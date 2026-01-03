ARG PHP_BASE_IMAGE=php:8.3-apache
FROM ${PHP_BASE_IMAGE}

ARG MOODLE_RELEASE_URL
ARG MOODLE_RELEASE_SHA256

ENV MOODLE_DIR=/var/www/html
ENV MOODLE_DATA_DIR=/var/www/moodledata

RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      libcurl4-openssl-dev \
      libfreetype6-dev \
      libicu-dev \
      libjpeg62-turbo-dev \
      libldap2-dev \
      libonig-dev \
      libpng-dev \
      libxml2-dev \
      libxslt1-dev \
      libzip-dev \
      unzip; \
    docker-php-ext-configure gd --with-freetype --with-jpeg; \
    docker-php-ext-install -j"$(nproc)" \
      curl \
      gd \
      intl \
      ldap \
      mbstring \
      mysqli \
      pdo_mysql \
      soap \
      xsl \
      zip; \
    a2enmod rewrite headers; \
    rm -rf /var/lib/apt/lists/*

# Moodle requires higher max_input_vars; default PHP values are too low, failing at install check.
RUN set -eu; \
    { \
      echo "max_input_vars=5000"; \
    } > /usr/local/etc/php/conf.d/moodle.ini

# Use the `public/` sub-directory as web root to match Moodle's recommended structure.
COPY docker/moodle/apache-moodle.conf /etc/apache2/sites-available/moodle.conf

RUN set -eu; \
    a2dissite 000-default; \
    a2ensite moodle

RUN set -eu; \
    if [ -z "${MOODLE_RELEASE_URL:-}" ] || [ -z "${MOODLE_RELEASE_SHA256:-}" ]; then \
      echo "MOODLE_RELEASE_URL and MOODLE_RELEASE_SHA256 must be set" >&2; \
      exit 1; \
    fi; \
    curl -fsSL "${MOODLE_RELEASE_URL}" -o /tmp/moodle.tgz; \
    echo "${MOODLE_RELEASE_SHA256}  /tmp/moodle.tgz" | sha256sum -c -; \
    mkdir -p "${MOODLE_DIR}"; \
    tar -xzf /tmp/moodle.tgz -C /tmp; \
    rm -rf "${MOODLE_DIR:?}/"*; \
    mv /tmp/moodle/* "${MOODLE_DIR}/"; \
    rm -rf /tmp/moodle /tmp/moodle.tgz; \
    chown -R www-data:www-data "${MOODLE_DIR}"

RUN set -eu; \
    mkdir -p "${MOODLE_DATA_DIR}"; \
    chown -R www-data:www-data "${MOODLE_DATA_DIR}"
