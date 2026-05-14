## Epidemiological model runner -- R.
##
## Consumes simulation jobs from Redis list ``epimodel:jobs:r`` (BRPOP via redux),
## solves SIS/SIR/SEIR/SIRS/SIDARTHE ODE systems with
## ``deSolve::ode`` (RK4, fixed step h = 1),
## and inserts compartment trajectories into YugabyteDB.

suppressPackageStartupMessages({
  library(deSolve)
  library(DBI)
  library(RPostgres)
  library(redux)
  library(jsonlite)
})

QUEUE <- "epimodel:jobs:r"
BRPOP_TIMEOUT_SEC <- 5L
ERROR_BACKOFF_SEC <- 2L

# Flag de oprire; R are signal handling limitat, ne bazam pe SIGTERM de la docker stop.
.running <- TRUE

sir_rhs <- function(t, state, parms) {
  invisible(t)
  with(as.list(c(state, parms)), {
    dS <- -beta * S * I / N
    dI <-  beta * S * I / N - gamma * I
    dR <-  gamma * I
    list(c(dS, dI, dR))
  })
}

sis_rhs <- function(t, state, parms) {
  invisible(t)
  with(as.list(c(state, parms)), {
    infections <- beta * S * I / N
    recoveries <- gamma * I
    dS <- -infections + recoveries
    dI <-  infections - recoveries
    list(c(dS, dI))
  })
}

seir_rhs <- function(t, state, parms) {
  invisible(t)
  with(as.list(c(state, parms)), {
    infections <- beta * S * I / N
    dS <- -infections
    dE <-  infections - sigma * E
    dI <-  sigma * E - gamma * I
    dR <-  gamma * I
    list(c(dS, dE, dI, dR))
  })
}

sirs_rhs <- function(t, state, parms) {
  invisible(t)
  with(as.list(c(state, parms)), {
    infections <- beta * S * I / N
    recoveries <- gamma * I
    waning <- xi * R
    dS <- -infections + waning
    dI <-  infections - recoveries
    dR <-  recoveries - waning
    list(c(dS, dI, dR))
  })
}

sidarthe_rhs <- function(t, state, parms) {
  invisible(t)
  with(as.list(c(state, parms)), {
    force <- (alpha * S_I + beta * D + gamma * A + delta * R) / N
    new_infections <- S * force
    dS <- -new_infections
    dI <- new_infections - (epsilon + zeta + lambda) * S_I
    dD <- epsilon * S_I - (eta + rho) * D
    dA <- zeta * S_I - (theta + mu + kappa) * A
    dR <- eta * D + theta * A - (nu + xi) * R
    dT <- mu * A + nu * R - (sigma + tau) * T
    dH <- lambda * S_I + rho * D + kappa * A + xi * R + sigma * T
    dE <- tau * T
    list(c(dS, dI, dD, dA, dR, dT, dH, dE))
  })
}

model_layout <- function(model_type) {
  if (identical(model_type, "sis")) {
    return(list(
      names = c("S", "I"),
      json_names = c("s", "i"),
      rhs = sis_rhs
    ))
  }
  if (identical(model_type, "sir")) {
    return(list(
      names = c("S", "I", "R"),
      json_names = c("s", "i", "r"),
      rhs = sir_rhs
    ))
  }
  if (identical(model_type, "seir")) {
    return(list(
      names = c("S", "E", "I", "R"),
      json_names = c("s", "e", "i", "r"),
      rhs = seir_rhs
    ))
  }
  if (identical(model_type, "sirs")) {
    return(list(
      names = c("S", "I", "R"),
      json_names = c("s", "i", "r"),
      rhs = sirs_rhs
    ))
  }
  if (identical(model_type, "sidarthe")) {
    return(list(
      names = c("S", "S_I", "D", "A", "R", "T", "H", "E"),
      json_names = c("s", "i", "d", "a", "r", "t", "h", "e"),
      rhs = sidarthe_rhs
    ))
  }
  stop(sprintf("unsupported model_type: %s", model_type))
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
  model_type <- if (!is.null(job$model_type)) job$model_type else "sidarthe"
  layout <- model_layout(model_type)
  parameters <- as.list(job$parameters)
  parameters <- lapply(parameters, as.numeric)
  N <- as.numeric(job$population_n)
  t_max <- as.integer(job$t_max)
  initials <- as.list(job$initial)
  y0 <- setNames(
    vapply(layout$json_names, function(name) {
      value <- initials[[name]]
      if (is.null(value)) 0 else as.numeric(value)
    }, numeric(1)),
    layout$names
  )

  dbExecute(conn, "UPDATE simulation_runs SET status = 'running' WHERE id = $1",
            params = list(sim_id))

  rss_before <- peak_rss_mb()
  wall_start <- proc.time()["elapsed"]
  cpu_start  <- proc.time()["user.self"] + proc.time()["sys.self"]

  times <- seq(0, t_max, by = 1)
  parms <- c(unlist(parameters), N = N)
  out <- ode(y = y0, times = times, func = layout$rhs, parms = parms, method = "rk4")

  wall_ms <- as.integer((proc.time()["elapsed"] - wall_start) * 1000)
  cpu_ms  <- as.integer(((proc.time()["user.self"] + proc.time()["sys.self"]) - cpu_start) * 1000)
  peak_mb <- max(peak_rss_mb(), rss_before)

  times_out <- as.integer(out[, "time"])

  dbWithTransaction(conn, {
    for (idx in seq_along(times_out)) {
      values <- as.list(pmax(0, as.numeric(out[idx, layout$names])))
      names(values) <- layout$json_names
      dbExecute(conn,
        "INSERT INTO simulation_results (simulation_id, t, compartments) VALUES ($1, $2, $3::jsonb)",
        params = list(sim_id, times_out[idx], toJSON(values, auto_unbox = TRUE)))
    }
    dbExecute(conn,
      "INSERT INTO benchmarks (simulation_id, wall_time_ms, cpu_time_ms, peak_memory_mb) VALUES ($1, $2, $3, $4)",
      params = list(sim_id, wall_ms, cpu_ms, peak_mb))
    dbExecute(conn,
      "UPDATE simulation_runs SET status = 'completed', completed_at = NOW() WHERE id = $1",
      params = list(sim_id))
  })

  message(sprintf("sim %s done: wall=%dms cpu=%dms mem=%.1fMB rows=%d",
                  sim_id, wall_ms, cpu_ms, peak_mb, length(times_out)))
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
