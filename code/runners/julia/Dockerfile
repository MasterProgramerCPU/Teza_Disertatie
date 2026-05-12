FROM julia:1.11

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Project.toml .
RUN julia --project=. -e 'using Pkg; Pkg.instantiate()'

COPY runner.jl .

CMD ["julia", "--project=.", "runner.jl"]
