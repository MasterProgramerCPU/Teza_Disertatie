#=
Epidemiological model runner -- Julia.

Consumes simulation jobs from Redis list `epimodel:jobs:julia` (BRPOP),
solves SIS/SIR/SEIR/SIRS/SIDARTHE ODE systems with
DifferentialEquations.jl (Tsit5, saveat=1),
and inserts compartment trajectories into YugabyteDB via LibPQ.
=#

using DifferentialEquations
using JSON3
using LibPQ
using Redis
using Dates

const QUEUE = "epimodel:jobs:julia"
const LANGUAGE = "julia"
const BRPOP_TIMEOUT_SEC = 5
const ERROR_BACKOFF_SEC = 2

mutable struct RunCtx
    running::Bool
end
const CTX = RunCtx(true)

function sir_rhs!(du, u, p, t)
    _ = t
    S, I, R = u
    beta = p["beta"]
    gamma = p["gamma"]
    N = p["N"]
    du[1] = -beta * S * I / N
    du[2] =  beta * S * I / N - gamma * I
    du[3] =  gamma * I
end

function sis_rhs!(du, u, p, t)
    _ = t
    S, I = u
    beta = p["beta"]
    gamma = p["gamma"]
    N = p["N"]
    infections = beta * S * I / N
    recoveries = gamma * I
    du[1] = -infections + recoveries
    du[2] =  infections - recoveries
end

function seir_rhs!(du, u, p, t)
    _ = t
    S, E, I, R = u
    beta = p["beta"]
    sigma = p["sigma"]
    gamma = p["gamma"]
    N = p["N"]
    infections = beta * S * I / N
    du[1] = -infections
    du[2] =  infections - sigma * E
    du[3] =  sigma * E - gamma * I
    du[4] =  gamma * I
end

function sirs_rhs!(du, u, p, t)
    _ = t
    S, I, R = u
    beta = p["beta"]
    gamma = p["gamma"]
    xi = p["xi"]
    N = p["N"]
    infections = beta * S * I / N
    recoveries = gamma * I
    waning = xi * R
    du[1] = -infections + waning
    du[2] =  infections - recoveries
    du[3] =  recoveries - waning
end

function sidarthe_rhs!(du, u, p, t)
    _ = t
    S, I, D, A, R, T, H, E = u
    _ = E
    N = p["N"]
    force = (p["alpha"] * I + p["beta"] * D + p["gamma"] * A + p["delta"] * R) / N
    new_infections = S * force

    du[1] = -new_infections
    du[2] = new_infections - (p["epsilon"] + p["zeta"] + p["lambda"]) * I
    du[3] = p["epsilon"] * I - (p["eta"] + p["rho"]) * D
    du[4] = p["zeta"] * I - (p["theta"] + p["mu"] + p["kappa"]) * A
    du[5] = p["eta"] * D + p["theta"] * A - (p["nu"] + p["xi"]) * R
    du[6] = p["mu"] * A + p["nu"] * R - (p["sigma"] + p["tau"]) * T
    du[7] = p["lambda"] * I + p["rho"] * D + p["kappa"] * A + p["xi"] * R + p["sigma"] * T
    du[8] = p["tau"] * T
    nothing
end

function model_layout(model_type::AbstractString)
    if model_type == "sis"
        return (state_names = ["s", "i"], rhs = sis_rhs!)
    elseif model_type == "sir"
        return (state_names = ["s", "i", "r"], rhs = sir_rhs!)
    elseif model_type == "seir"
        return (state_names = ["s", "e", "i", "r"], rhs = seir_rhs!)
    elseif model_type == "sirs"
        return (state_names = ["s", "i", "r"], rhs = sirs_rhs!)
    elseif model_type == "sidarthe"
        return (state_names = ["s", "i", "d", "a", "r", "t", "h", "e"], rhs = sidarthe_rhs!)
    end
    error("unsupported model_type: $model_type")
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
    model_type = String(get(job, :model_type, "sidarthe"))
    layout = model_layout(model_type)
    params = Dict{String, Float64}(String(k) => Float64(v) for (k, v) in pairs(job[:parameters]))
    N = Float64(job[:population_n])
    t_max = Int(job[:t_max])
    params["N"] = N
    initial = Dict{String, Float64}(String(k) => Float64(v) for (k, v) in pairs(job[:initial]))
    y0 = Float64[get(initial, name, 0.0) for name in layout.state_names]

    LibPQ.execute(conn,
        "UPDATE simulation_runs SET status = 'running' WHERE id = \$1",
        [sim_id])

    rss_before = peak_rss_mb()
    wall_start = time_ns()
    cpu_start  = time()  # process CPU not directly exposed; use elapsed as fallback

    prob = ODEProblem(layout.rhs, y0, (0.0, Float64(t_max)), params)
    sol = solve(prob, Tsit5(); saveat = 0:1.0:t_max, reltol = 1e-8, abstol = 1e-10)

    wall_ms = round(Int, (time_ns() - wall_start) / 1_000_000)
    cpu_ms  = round(Int, (time() - cpu_start) * 1000)
    peak_mb = max(peak_rss_mb(), rss_before)

    LibPQ.execute(conn, "BEGIN")
    try
        stmt = LibPQ.prepare(conn,
            "INSERT INTO simulation_results (simulation_id, t, compartments) VALUES (\$1, \$2, \$3::jsonb)")
        for (idx, t) in enumerate(sol.t)
            u = sol.u[idx]
            values = Dict(name => max(0.0, Float64(u[pos])) for (pos, name) in enumerate(layout.state_names))
            LibPQ.execute(stmt, (sim_id, Int(t), JSON3.write(values)))
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
