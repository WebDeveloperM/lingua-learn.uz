# https for the Learn English site: nginx in front of Django, with a certificate authority of its own
# (see 05-local-certs.sh, site.conf and stream.conf)
FROM nginx:1.27-alpine

RUN apk add --no-cache openssl \
    && rm -f /etc/nginx/conf.d/default.conf

COPY site.conf /etc/nginx/conf.d/site.conf
COPY stream.conf /etc/nginx/stream.d/ports.conf
COPY 05-local-certs.sh /docker-entrypoint.d/05-local-certs.sh

# the "stream" part of nginx (plain TCP, used to share port 8000), and the files may have been saved with Windows line endings
RUN printf '\nstream {\n    include /etc/nginx/stream.d/*.conf;\n}\n' >> /etc/nginx/nginx.conf \
    && sed -i 's/\r$//' /etc/nginx/conf.d/site.conf /etc/nginx/stream.d/ports.conf /docker-entrypoint.d/05-local-certs.sh \
    && chmod +x /docker-entrypoint.d/05-local-certs.sh

EXPOSE 8000 8443
