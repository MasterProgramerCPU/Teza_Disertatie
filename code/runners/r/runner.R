## SIR runner -- R.
##
## Consumes simulation jobs from Redis list ``sir:jobs:r`` (BRPOP via redux),
## solves the SIR ODE with ``deSolve::ode`` (RK4, fixed step h = 1), and
## bulk-inserts results into YugabyteDB.

suppressPackageStartupMessages({
  library(deSolve)
  library(DBI)
  library(RPostgres)
  library(redux)
  library(jsonlite)
})

QUEUE <- "sir:jobs:r"
LANGUAGE <- "r"
BRPOP_TIMEOUT_SEC <- 5L
ERROR_BACKOFF_SEC <- 2L

# graceful shutdown flag
.running <- TRUE
handle_signal <- function() {
  message("signal received, shutting down")
  .running <<- FALSE
}
# best effort: R has limited signal handling; rely on docker stop SIGTERM = exit

sir_rhs <- function(t, state, parms) {
  with(as.list(c(state, parms)), {
    dS <- -beta * S * I / N
    dI <-  beta * S * I / N - gamma * I
    dR <-  gamma * I
    list(c(dS, dI, dR))
  })
}

peak_rss_mb <- function() {
  # /proc/self/status VmHWM is Linux-only; on macOS fall back to gc()
  status <- tryCatch(readLines("/proc/self/status", warn = FALSE), error = function(e) NULL)
  if (!is.null(status)) {
    line <- grep("^VmHWM:", status, value = TRUE)
    if (length(line) == 1) {
      kb <- as.numeric(sub("[^0-9]+([0-9]+).*", "\\1", line))
      return(kb / 1024)
    }
  }
  used_mb <- sum(gc()[, 2])
  used_mb
}

parse_dsn <- function(dsn) {
  # postgres://user:pass@host:port/db?sslmode=disable
  m <- regmatches(dsn, regexec(
    "postgres(?:ql)?://([^:]+):([^@]*)@([^:/]+):([0-9]+)/([^?]+)", dsn
  ))[[1]]
  if (length(m) < 6) stop(sprintf("invalid DSN: %s", dsn))
  list(user = m[2], password = m[3], host = m[4],
       port = as.integer(m[5]), dbname = m[6])
}

db_connect <- function(dsn) {
  p <- parse_dsn(dsn)
  dbConnect(RPostgres::Postgres(),
            host = p$host, port = p$port, dbname = p$dbname,
            user = p$user, password = p$password)
}

run_simulation <- function(conn, job) {
  sim_id <- job$simulation_id
  beta <- as.numeric(job$beta)
  gamma <- as.numeric(job$gamma)
  N <- as.numeric(job$population_n)
  t_max <- as.integer(job$t_max)
  y0 <- c(S = as.numeric(job$s0),
          I = as.numeric(job$i0),
          R = as.numeric(job$r0))

  dbExecute(conn, "UPDATE simulation_runs SET status = 'running' WHERE id = $1",
            params = list(sim_id))

  rss_before <- peak_rss_mb()
  wall_start <- proc.time()["elapsed"]
  cpu_start  <- proc.time()["user.self"] + proc.time()["sys.self"]

  times <- seq(0, t_max, by = 1)
  parms <- c(beta = beta, gamma = gamma, N = N)
  out <- ode(y = y0, times = times, func = sir_rhs, parms = parms, method = "rk4")

  wall_ms <- as.integer((proc.time()["elapsed"] - wall_start) * 1000)
  cpu_ms  <- as.integer(((proc.time()["user.self"] + proc.time()["sys.self"]) - cpu_start) * 1000)
  peak_mb <- max(peak_rss_mb(), rss_before)

  results <- data.frame(
    simulation_id = sim_id,
    t = as.integer(out[, "time"]),
    s = as.numeric(out[, "S"]),
    i = as.numeric(out[, "I"]),
    r = as.numeric(out[, "R"]),
    stringsAsFactors = FALSE
  )

  dbWithTransaction(conn, {
    dbAppendTable(conn, "simulation_results", results)
    dbExecute(conn,
      "INSERT INTO benchmarks (simulation_id, wall_time_ms, cpu_time_ms, peak_memory_mb) VALUES ($1, $2, $3, $4)",
      params = list(sim_id, wall_ms, cpu_ms, peak_mb))
    dbExecute(conn,
      "UPDATE simulation_runs SET status = 'completed', completed_at = NOW() WHERE id = $1",
      params = list(sim_id))
  })

  message(sprintf("sim %s done: wall=%dms cpu=%dms mem=%.1fMB rows=%d",
                  sim_id, wall_ms, cpu_ms, peak_mb, nrow(results)))
}

mark_failed <- function(conn, sim_id, msg) {
  tryCatch(
    dbExecute(conn,
      "UPDATE simulation_runs SET status = 'failed', error_message = $1, completed_at = NOW() WHERE id = $2",
      params = list(substr(msg, 1, 2000), sim_id)),
    error = function(e) message(sprintf("could not mark failed: %s", e$message))
  )
}

main <- function() {
  redis_url <- Sys.getenv("REDIS_URL", "redis://redis:6379/0")
  db_dsn_env <- Sys.getenv("DATABASE_URL", "")

  # redux uses host/port/db number; parse URL
  m <- regmatches(redis_url, regexec(
    "redis://(?:[^@]*@)?([^:/]+):([0-9]+)(?:/([0-9]+))?", redis_url
  ))[[1]]
  if (length(m) < 4) stop(sprintf("invalid REDIS_URL: %s", redis_url))
  rdb <- redux::hiredis(host = m[2], port = as.integer(m[3]),
                        db = if (m[4] == "") 0L else as.integer(m[4]))
  rdb$PING()
  message(sprintf("runner-r connected to redis, consuming %s", QUEUE))

  while (.running) {
    item <- tryCatch(rdb$BRPOP(QUEUE, BRPOP_TIMEOUT_SEC),
                     error = function(e) {
                       message(sprintf("redis error: %s", e$message))
                       Sys.sleep(ERROR_BACKOFF_SEC)
                       NULL
                     })
    if (is.null(item)) next

    raw <- item[[2]]
    job <- tryCatch(fromJSON(raw), error = function(e) {
      message(sprintf("invalid job json: %s", e$message))
      NULL
    })
    if (is.null(job)) next

    sim_id <- if (!is.null(job$simulation_id)) job$simulation_id else "?"
    dsn <- if (!is.null(job$db_dsn) && nzchar(job$db_dsn)) job$db_dsn else db_dsn_env
    if (!nzchar(dsn)) {
      message(sprintf("sim %s: no db_dsn", sim_id))
      next
    }

    conn <- tryCatch(db_connect(dsn), error = function(e) {
      message(sprintf("sim %s db connect failed: %s", sim_id, e$message))
      NULL
    })
    if (is.null(conn)) next

    tryCatch({
      run_simulation(conn, job)
    }, error = function(e) {
      message(sprintf("sim %s failed: %s", sim_id, e$message))
      mark_failed(conn, sim_id, e$message)
    }, finally = {
      dbDisconnect(conn)
    })
  }
  message("runner-r stopped")
}

main()
