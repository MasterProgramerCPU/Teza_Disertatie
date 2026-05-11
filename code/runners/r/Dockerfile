FROM r-base:4.4.2

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        libssl-dev \
        libcurl4-openssl-dev \
        libxml2-dev \
        libhiredis-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY install_packages.R .
RUN Rscript install_packages.R

COPY runner.R .

CMD ["Rscript", "runner.R"]
