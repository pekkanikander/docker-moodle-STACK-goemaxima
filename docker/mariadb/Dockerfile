ARG MARIADB_IMAGE=mariadb:11.4
FROM ${MARIADB_IMAGE}

ARG MARIADB_UID=2001
ARG MARIADB_GID=2001

RUN set -eu; \
    old_uid="$(id -u mysql)"; \
    old_gid="$(id -g mysql)"; \
    if [ "${MARIADB_GID}" != "${old_gid}" ]; then \
      groupmod -g "${MARIADB_GID}" mysql; \
    fi; \
    if [ "${MARIADB_UID}" != "${old_uid}" ]; then \
      usermod -u "${MARIADB_UID}" -g "${MARIADB_GID}" mysql; \
    fi; \
    find / -xdev -uid "${old_uid}" -exec chown -h "${MARIADB_UID}:${MARIADB_GID}" {} +; \
    find / -xdev -gid "${old_gid}" -exec chgrp -h "${MARIADB_GID}" {} +; \
    true
