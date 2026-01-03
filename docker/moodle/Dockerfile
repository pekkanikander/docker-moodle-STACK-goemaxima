ARG PHP_BASE_IMAGE=php:8.3-apache
FROM ${PHP_BASE_IMAGE}

ARG MOODLE_RELEASE_URL
ARG MOODLE_RELEASE_SHA256
ARG STACK_PLUGIN_URL
ARG STACK_PLUGIN_SHA256
ARG STACK_BEHAVIOUR_DFEXPLICIT_URL
ARG STACK_BEHAVIOUR_DFEXPLICIT_SHA256
ARG STACK_BEHAVIOUR_DFCBMEXPLICIT_URL
ARG STACK_BEHAVIOUR_DFCBMEXPLICIT_SHA256
ARG STACK_BEHAVIOUR_ADAPTIVEMULTIPART_URL
ARG STACK_BEHAVIOUR_ADAPTIVEMULTIPART_SHA256

ENV MOODLE_DIR=/var/www/html
ENV MOODLE_PUBLIC_DIR=/var/www/html/public
ENV MOODLE_DATA_DIR=/var/www/moodledata

RUN set -eu; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      cron \
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
      echo "display_errors=1"; \
      echo "log_errors=1"; \
      echo "max_input_vars=5000"; \
    } > /usr/local/etc/php/conf.d/moodle.ini

# Use the `public/` sub-directory as web root to match Moodle's recommended structure.
COPY docker/moodle/apache-moodle.conf /etc/apache2/sites-available/moodle.conf
COPY docker/moodle/moodle-cron.sh /usr/local/bin/moodle-cron.sh

RUN set -eu; \
    a2dissite 000-default; \
    a2ensite moodle

RUN set -eu; \
    chmod 0755 /usr/local/bin/moodle-cron.sh; \
    { \
      echo "SHELL=/bin/sh"; \
      echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"; \
      echo "* * * * * www-data /usr/local/bin/moodle-cron.sh >/proc/1/fd/1 2>/proc/1/fd/2"; \
    } > /etc/cron.d/moodle; \
    chmod 0644 /etc/cron.d/moodle

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
    if [ -z "${STACK_PLUGIN_URL:-}" ]; then \
      echo "STACK_PLUGIN_URL must be set" >&2; \
      exit 1; \
    fi; \
    install_plugin() { \
      url="$1"; \
      sha="$2"; \
      target="$3"; \
      if [ -z "$url" ]; then \
        return 0; \
      fi; \
      tmpdir="$(mktemp -d)"; \
      case "$url" in \
        *.zip) \
          archive="$tmpdir/plugin.zip"; \
          curl -fsSL "$url" -o "$archive"; \
          if [ -n "$sha" ]; then \
            echo "${sha}  $archive" | sha256sum -c -; \
          fi; \
          unzip -q "$archive" -d "$tmpdir"; \
          ;; \
        *.tar.gz|*.tgz) \
          archive="$tmpdir/plugin.tgz"; \
          curl -fsSL "$url" -o "$archive"; \
          if [ -n "$sha" ]; then \
            echo "${sha}  $archive" | sha256sum -c -; \
          fi; \
          tar -xzf "$archive" -C "$tmpdir"; \
          ;; \
        *) \
          echo "Unsupported plugin archive: $url" >&2; \
          exit 1; \
          ;; \
      esac; \
      src_dir="$(find "$tmpdir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"; \
      if [ -z "$src_dir" ]; then \
        echo "Failed to unpack $url" >&2; \
        exit 1; \
      fi; \
      mkdir -p "$target"; \
      cp -a "$src_dir/." "$target/"; \
      rm -rf "$tmpdir"; \
    }; \
    install_plugin "${STACK_PLUGIN_URL}" "${STACK_PLUGIN_SHA256}" "${MOODLE_PUBLIC_DIR}/question/type/stack"; \
    install_plugin "${STACK_BEHAVIOUR_DFEXPLICIT_URL}" "${STACK_BEHAVIOUR_DFEXPLICIT_SHA256}" "${MOODLE_PUBLIC_DIR}/question/behaviour/dfexplicitvaildate"; \
    install_plugin "${STACK_BEHAVIOUR_DFCBMEXPLICIT_URL}" "${STACK_BEHAVIOUR_DFCBMEXPLICIT_SHA256}" "${MOODLE_PUBLIC_DIR}/question/behaviour/dfcbmexplicitvaildate"; \
    install_plugin "${STACK_BEHAVIOUR_ADAPTIVEMULTIPART_URL}" "${STACK_BEHAVIOUR_ADAPTIVEMULTIPART_SHA256}" "${MOODLE_PUBLIC_DIR}/question/behaviour/adaptivemultipart"; \
    chown -R www-data:www-data "${MOODLE_DIR}"

RUN set -eu; \
    mkdir -p "${MOODLE_DATA_DIR}"; \
    chown -R www-data:www-data "${MOODLE_DATA_DIR}"
