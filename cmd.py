#!/usr/bin/env python3
from os import listdir
from os.path import isfile
from shutil import copyfile
from subprocess import CalledProcessError, run
from sys import argv, version_info


class CmdHandler:
    def version_info(self, *args, **kwargs):
        print(f"{__file__}: Python {'.'.join([str(i) for i in version_info[:3]])}")

    def available_commands(self, *args, **kwargs):
        print(
            *tuple(
                ["Available Commands:"]
                + [f for f in dir(self) if callable(getattr(self, f)) and f[0] != "_"]
            ),
            sep="\n* ",
        )

    def _run(self, *args, **kwargs):
        return run(*args, text=True, check=True)

    def _get_compose_project_name(self):
        # this would be cleaner with the python-dotenv package
        with open(".env", "r") as f:
            for line in f.readlines():
                if not line.startswith("COMPOSE_PROJECT_NAME"):
                    continue
                return line.replace(" ", "").split("=")[1].replace("\n", "")
        raise ValueError("COMPOSE_PROJECT_NAME not specified in .env file")

    def _get_docker_compose_args(self):
        compose_args = []
        compose_files = ["./docker-compose.yml"]
        for file in listdir("./compositions"):
            if not file.startswith("docker-compose.") or not file.endswith(".yml"):
                continue
            compose_files.append(f"./compositions/{file}")
        for file in compose_files:
            compose_args.append("-f")
            compose_args.append(file)
        return compose_args

    def docker_compose_up(self, *args, **kwargs):
        self._run(["docker-compose"] + self._get_docker_compose_args() + ["up", "-d"])

    def docker_compose_down(self, *args, **kwargs):
        self._run(["docker-compose"] + self._get_docker_compose_args() + ["down"])

    def docker_compose_reload(self, *args, **kwargs):
        self.docker_compose_down()
        self._run(["docker-compose", "rm", "-f"])
        self.docker_compose_up()

    def registry_create_password(self, usr, pw, *args, **kwargs):
        self.docker_compose_up()
        compose_name = self._get_compose_project_name()
        docker = ["docker", "exec", f"{compose_name}_registry"]
        self._run(docker + ["apk", "add", "apache2-utils"])
        self._run(docker + ["htpasswd", "-B", "-b", "-c", "registry.password", usr, pw])

    def certbot_new_domain(self, domain, email, *args, **kwargs):
        self.docker_compose_up()
        compose_name = self._get_compose_project_name()
        docker = ["docker", "exec", f"{compose_name}_certbot"]
        try:
            self._run(docker + ["rm", "-rf", f"/etc/letsencrypt/live/{domain}"])
        except CalledProcessError:
            pass
        self._run(
            docker
            + [
                "certbot",
                "certonly",
                "--email",
                email,
                "-d",
                domain,
                "--cert-name",
                domain,
                "--webroot",
                "-w",
                "/var/www/certbot",
                "--rsa-key-size",
                "4096",
                "--agree-tos",
                "--force-renewal",
                "--renew-by-default",
                "--preferred-challenges",
                "http",
                "--non-interactive",
            ]
        )
        self.docker_compose_reload()


if __name__ == "__main__":
    if len(argv) < 2:
        argv.append("available_commands")
        if not hasattr(CmdHandler, argv[1]):
            raise ValueError("No argument passed to command script")
    if not (hasattr(CmdHandler, argv[1]) and callable(getattr(CmdHandler, argv[1]))):
        raise ValueError(f"The requested command {argv[1]} was not found")
    if not isfile("./.env"):
        copyfile("./default.env", ".env")
    handler = CmdHandler()
    result = getattr(CmdHandler(), argv[1])(*argv[2:])
    print(f"{argv[1]} completed{': ' + result if result else ''}")
