# Side Project Deployment Template

This repository is a template for a simple single-server multi-site deployment
scheme, based on [NGINX](https://nginx.org/) and
[Docker](https://docs.docker.com/compose/). This template makes it easier to
manage multiple projects on a single server by setting up an extensible
composition that serves most needs out of the box.

## Usage

Make sure that you have Python 3.x and Docker Compose installed. Clone the
repository and run `python cmd.py docker_compose up`. See "Extending" for
instructions on extending the template to include other containers.

## Containers

This template includes four pre-configured Docker containers.

### Nginx

[NGINX](https://hub.docker.com/_/nginx) is used to direct incoming web traffic
to the appropriate project containers, including handling HTTP to HTTPS
redirects and SSL certificates. The entrypoint script generates self-signed
certificates for each domain given in the configuration files (Certbot is used
to generate live certificates), which allows NGINX to start before live
certificates are generated.

### Certbot

[Certbot](https://hub.docker.com/r/certbot/certbot) is included and configured
to automatically renew SSL certificates. It is included as part of the
[Nginx configuration](./default/nginx/docker-compose.nginx.yml).

### Docker Registry

A [Docker registry container](https://hub.docker.com/_/registry) is included in
this project. It serves as an easy way to manage project images, and as an
example of how this template can be extended to deploy other containers. This
registry requires authentication by default, and is configured to be served at
any host with a `registry.` subdomain.

When deploying this template, be sure to configure the SSL cert paths in
[registry.nginx](./default/registry/registry.nginx) to match the correct
hostname.

Once the container is running, the `htpasswd` authentication for the container
can be set by running `cmd.py registry_create_password <user> <pass>`.

See
[docker-compose.registry.yml](./default/registry/docker-compose.registry.yml)
and [registry.nginx](./default/registry/registry.nginx) for more.

### Semaphore

Semaphore is a simple Python server that facilitates remotely updating the
composition (for example, as part of a CI/CD process). By default, it is
configured to be served at any host with a `semaphore.` subdomain. Requests to
the server require a password, set via the `SEMAPHORE_PASSWORD` environment
variable.

Making a `POST` request to `semaphore.domain.com/?<SEMAPHORE_PASSWORD>` with a
plaintext body containing the name and tag of a Docker image or the name of a
container in the composition will queue matching containers to be updated and
rebuilt. This update can be triggered by `cmd.py update_from_semaphore`, and can
be run on a schedule with
`cmd.py schedule_background_update <interval_minutes>`.

For example, a server at `domain.com` running `myimage:latest` and
`nohup python cmd.py schedule_background_update 5 &` could be updated remotely
with `curl -X POST http://semaphore.domain.com/?<PASSWORD> -d "myimage:latest"`.

## Commands

Management commands are collected in [cmd.py](./cmd.py), which is written for
Python 3.x. Python is chosen for its ease of execution, large standard library,
and cross-platform support.

- `cmd.py available_commands`: Lists available commands.
- `cmd.py docker_compose`: Takes arguments `up`, `down`, and `reload`. Manages a
  Docker composition that includes all `docker-compose.yml` specifications
  enumerated in `./files/*.files.csv`.
- `cmd.py registry_create_password <username> <password>`: Sets the
  authentication for the Docker registry to the given username and password.
- `cmd.py certbot_new_domain <domain> <email>`: Gets a new certificate for the
  given domain, registered to the given email. This uses an HTTP verification
  challenge, which means wildcard certificates cannot be generated.
- `cmd.py update_from_semaphore`: Update and restart containers based on
  received data from Semaphore. `schedule_background_update <interval_minutes>`
  will run this command at regular intervals.

## .env

This .env file is loaded across all docker-compose files. Therefore, any
environment variables referenced in these files should be included here. If no
.env file is present in the directory, the `default.env` file will be copied to
replace it.

- `COMPOSE_PROJECT_NAME`: Ensures that the container, network, and volume names
  are consistent
- [`CSR_SUBJ`](https://www.openssl.org/docs/man1.0.2/man1/openssl-req.html):
  Used by the NGINX entrypoint to generate self-signed certs.
- `SIDEPROJECTDEPLOYMENT_ENV_PATH`: Path to the shared .env file (relative to
  this repository's root)
- `SIDEPROJECTDEPLOYMENT_TEMPDIR`: Path to the temporary directory, where
  extension files are copied and mounted from.
- `SEMAPHORE_PASSWORD`: Password to require for updating Semaphore.

## Extending

New Docker images can be included in this composition by including an entry in
the [`./files/`](./files) directory (with the extension `.files.csv`). The CSV
should contain a list of source files and their destination - files will be
copied to the path specified by `SIDEPROJECTDEPLOYMENT_TEMPDIR`. If the second
line of the `*.files.csv` file is structured as `$GIT,<path>`, then the script
will attempt to pull from the git repository at the given path before copying
files.

Any `docker-compose.*.yml` files are automatically included in the project
composition when `docker-compose` is run from [cmd.py](./cmd.py). Any files with
the destination `nginx/*.nginx` will be included as fragments in
[`nginx.nginx`](./default/nginx/nginx.nginxconf).

A minimal extension consists of three files: a `*.files.csv` entry in `./files`,
a `docker-compose.*.yml` file, and an Nginx fragment. Refer
to[`default/registry/`](./default/registry/) and
[`files/registry.files.csv`](./files/registry.files.csv) as an example.

By default, new docker-compose files inherit the `.env` file and the
composition's network settings and . This allows NGINX to direct web traffic to
specific containers.

An example NGINX configuration is as follows:

```nginx
upstream example {
  server example:8000;
}

server {
  listen              443 ssl http2;
  listen              [::]:443 ssl http2;
  server_name         example.com;
  ssl_certificate     /etc/nginx/ssl/live/example.com/fullchain.pem;
  ssl_certificate_key /etc/nginx/ssl/live/example.com/privkey.pem;

  location / {
    proxy_pass http://example;
  }
}
```

Note the `upstream` directive, which directs traffic to a container. This means
that SSL certificates only need to be managed by the NGINX container, and
sibling containers can ignore it safely. The `ssl_certificate` directives
provide a path to the SSL certificates, which are generated at startup, and can
be replaced by Certbot. For the cert file to be generated at startup, the
`ssl_certificate` directive must target a file matching
`/etc/nginx/ssl/live/<domain>/fullchain.pem`, where `<domain>` is a valid
(sub)domain. This path matches that generated by Certbot, so that self-signed
and live certificates share a path.

An example docker-compose file is as follows:

```yaml
volumes:
  persistent:

services:
  registry:
    container_name: ${COMPOSE_PROJECT_NAME:-deployment}_example
    image: alpine:latest
    restart: always
    volumes:
      - persistent:/data
    environment:
      VARIABLE: "${VARIABLE:-default}"
```

Since the file will be copied to `SIDEPROJECTDEPLOYMENT_TEMPDIR`, any path
specifications should be relative to the other destination paths specified in
`./files/*.files.csv`.

Environment variables should be given defaults, and defined in this repository's
`.env` file (or, of course, on the server itself).

Refer to [`./files/`](./files), [`./default/registry/`](./default/registry), and
[`./default/semaphore/`](./default/semaphore) for examples of extensions.
