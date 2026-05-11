#=
SIR runner -- Julia.

Consumes simulation jobs from Redis list `sir:jobs:julia` (BRPOP),
solves the SIR ODE with DifferentialEquations.jl (Tsit5, saveat=1),
and bulk-inserts results into YugabyteDB via LibPQ.
=#

using DifferentialEquations
using JSON3
using LibPQ
using Redis
using Dates

const QUEUE = "sir:jobs:julia"
const LANGUAGE = "julia"
const BRPOP_TIMEOUT_SEC = 5
const ERROR_BACKOFF_SEC = 2

mutable struct RunCtx
    running::Bool
end
const CTX = RunCtx(true)

function sir_rhs!(du, u, p, t)
    S, I, R = u
    β, γ, N = p
    du[1] = -β * S * I / N
    du[2] =  β * S * I / N - γ * I
    du[3] =  γ * I
end

peak_rss_mb() = Sys.maxrss() / (1024 * 1024)

function parse_redis_url(url::AbstractString)
    m = match(r"^redis://(?:[^@]*@)?(?<host>[^:/]+):(?<port>\d+)(?:/(?<db>\d+))?$", url)
    m === nothing && error("invalid REDIS_URL: $url")
    (host = m[:host],
     port = parse(Int, m[:port]),
     db   = m[:db] === nothing ? 0 : parse(Int, m[:db]))
end

function run_simulation(conn::LibPQ.Connection, job::Dict{Symbol, Any})
    sim_id = String(job[:simulation_id])
    β = Float64(job[:beta])
    γ = Float64(job[:gamma])
    N = Float64(job[:population_n])
    t_max = Int(job[:t_max])
    y0 = Float64[job[:s0], job[:i0], job[:r0]]

    LibPQ.execute(conn,
        "UPDATE simulation_runs SET status = 'running' WHERE id = \$1",
        [sim_id])

    rss_before = peak_rss_mb()
    wall_start = time_ns()
    cpu_start  = time()  # process CPU not directly exposed; use elapsed as fallback

    prob = ODEProblem(sir_rhs!, y0, (0.0, Float64(t_max)), (β, γ, N))
    sol = solve(prob, Tsit5(); saveat = 0:1.0:t_max, reltol = 1e-8, abstol = 1e-10)

    wall_ms = round(Int, (time_ns() - wall_start) / 1_000_000)
    cpu_ms  = round(Int, (time() - cpu_start) * 1000)
    peak_mb = max(peak_rss_mb(), rss_before)

    LibPQ.execute(conn, "BEGIN")
    try
        stmt = LibPQ.prepare(conn,
            "INSERT INTO simulation_results (simulation_id, t, s, i, r) VALUES (\$1, \$2, \$3, \$4, \$5)")
        for (idx, t) in enumerate(sol.t)
            u = sol.u[idx]
            LibPQ.execute(stmt, (sim_id, Int(t), u[1], u[2], u[3]))
        end
        LibPQ.execute(conn,
            "INSERT INTO benchmarks (simulation_id, wall_time_ms, cpu_time_ms, peak_memory_mb) VALUES (\$1, \$2, \$3, \$4)",
            [sim_id, wall_ms, cpu_ms, peak_mb])
        LibPQ.execute(conn,
            "UPDATE simulation_runs SET status = 'completed', completed_at = NOW() WHERE id = \$1",
            [sim_id])
        LibPQ.execute(conn, "COMMIT")
    catch e
        LibPQ.execute(conn, "ROLLBACK")
        rethrow(e)
    end

    println("sim $sim_id done: wall=$(wall_ms)ms cpu=$(cpu_ms)ms mem=$(round(peak_mb, digits=1))MB rows=$(length(sol.t))")
end

function mark_failed(conn::LibPQ.Connection, sim_id::AbstractString, msg::AbstractString)
    try
        LibPQ.execute(conn,
            "UPDATE simulation_runs SET status = 'failed', error_message = \$1, completed_at = NOW() WHERE id = \$2",
            [first(msg, 2000), sim_id])
    catch e
        @warn "could not mark failed" exception=e
    end
end

function main()
    redis_url = get(ENV, "REDIS_URL", "redis://redis:6379/0")
    db_dsn_env = get(ENV, "DATABASE_URL", "")
    rinfo = parse_redis_url(redis_url)
    rcli = RedisConnection(host = rinfo.host, port = rinfo.port, db = rinfo.db)
    Redis.ping(rcli)
    println("runner-julia connected to redis, consuming $QUEUE")

    while CTX.running
        item = try
            Redis.brpop(rcli, [QUEUE], BRPOP_TIMEOUT_SEC)
        catch e
            @warn "redis error" exception=e
            sleep(ERROR_BACKOFF_SEC)
            nothing
        end
        item === nothing && continue
        # Redis.brpop returns Vector{String} [queue_name, payload] or nil
        length(item) < 2 && continue
        raw = item[2]

        job = try
            JSON3.read(raw, Dict{Symbol, Any})
        catch e
            @warn "invalid job json" exception=e
            continue
        end

        sim_id = get(job, :simulation_id, "?")
        dsn = get(job, :db_dsn, "")
        if isempty(dsn)
            dsn = db_dsn_env
        end
        if isempty(dsn)
            @warn "no db_dsn for sim" sim_id
            continue
        end

        conn = try
            LibPQ.Connection(dsn)
        catch e
            @warn "db connect failed" sim_id exception=e
            continue
        end
        try
            run_simulation(conn, job)
        catch e
            @warn "sim failed" sim_id exception=e
            mark_failed(conn, String(sim_id), sprint(showerror, e))
        finally
            close(conn)
        end
    end
    println("runner-julia stopped")
end

main()
