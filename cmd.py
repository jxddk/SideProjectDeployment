#!/usr/bin/env python
import subprocess
from datetime import datetime
from json import loads
from os import chdir, environ, getcwd, makedirs, remove, walk
from os.path import abspath, dirname, isfile, join
from shutil import copyfile
from sys import argv, version_info
from time import sleep, time
from typing import List, Union
from warnings import warn


class CmdHandler:
    ROOT_DIRECTORY = abspath(dirname(__file__))
    TEMP_DIRECTORY = abspath(
        environ.get("SIDEPROJECTDEPLOYMENT_TEMPDIR", join(ROOT_DIRECTORY, "./.temp"))
    )
    FILES_DIRECTORY = abspath(join(ROOT_DIRECTORY, "./files"))
    ENV_PATH = abspath(
        environ.get("SIDEPROJECTDEPLOYMENT_ENV_PATH", join(ROOT_DIRECTORY, "./.env"))
    )
    DEFAULT_ENV_PATH = abspath(join(ROOT_DIRECTORY, "./.env"))

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

    def _run(self, cmd, **kwargs) -> Union[str, None]:
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                universal_newlines=True,
                text=True,
            )
        except TypeError as e:
            raise TypeError(f"TypeError with commands ({cmd}): {str(e)}")
        lines = []
        for line in iter(process.stdout.readline, ""):
            lines.append(line)
        process.stdout.close()
        return_code = process.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, cmd)
        if len(lines) > 0:
            return "".join(lines)

    def _get_compose_project_name(self):
        with open(".env", "r") as f:
            for line in f.readlines():
                if not line.startswith("COMPOSE_PROJECT_NAME"):
                    continue
                return line.replace(" ", "").split("=")[1].replace("\n", "")
        raise ValueError("COMPOSE_PROJECT_NAME not specified in .env file")

    def _generate_temp_directory(self):
        src_paths = [abspath(join(self.ROOT_DIRECTORY, "docker-compose.yml"))]
        dest_paths = [abspath(join(self.TEMP_DIRECTORY, "docker-compose.yml"))]
        for root, dirs, files in walk(self.FILES_DIRECTORY):
            for file in files:
                if not file.endswith(".files.csv"):
                    continue
                file_path = join(root, file)
                with open(file_path, "r") as f:
                    line_counter = 0
                    for line in f.readlines():
                        line_counter += 1
                        if line_counter <= 1:
                            continue
                        line = line.rstrip()
                        line_data = line.split(",")
                        if len(line_data) != 2:
                            raise ValueError(
                                f"Invalid number of items in line {line_counter}"
                                f" of {file_path}"
                            )
                        if line_counter == 2 and line_data[0] == "$GIT":
                            if not line_data[1].endswith(".git"):
                                line_data[1] = join(line_data[1], ".git")
                            try:
                                self._run(
                                    [
                                        "git",
                                        "--git-dir",
                                        line_data[1],
                                        "pull",
                                        "--ff-only",
                                    ]
                                )
                            except subprocess.CalledProcessError as e:
                                warn(
                                    f"Error while pulling git repository at {line_data[1]}: {e}"
                                )
                            continue
                        src_paths.append(line_data[0])
                        if line_data[1] in dest_paths:
                            raise FileExistsError(
                                f"Duplicate dest path {line_data[1]}"
                                f" on line {line_counter} of {file_path}"
                            )
                        dest_paths.append(line_data[1])

        if len(src_paths) != len(dest_paths):
            raise ValueError(
                f"Length of src paths ({len(src_paths)} does not match"
                f"length of dest paths {len(dest_paths)}."
            )

        for root, dirs, files in walk(self.TEMP_DIRECTORY):
            for file in files:
                file_path = join(root, file)
                remove(file_path)

        for index in range(len(src_paths)):
            dest_path = abspath(join(self.TEMP_DIRECTORY, dest_paths[index]))
            src_path = abspath(src_paths[index])
            makedirs(dirname(dest_path), exist_ok=True)
            copyfile(src_path, dest_path)

    def docker_compose(self, *args, **kwargs):
        docker_args = self._docker_compose_args
        if type(args) == tuple:
            args = list(args)
        if args == ["up"]:
            args.append("-d")
        if args == ["reload"]:
            self.docker_compose("pull")
            self.docker_compose("down")
            self.docker_compose("up")
        else:
            starting_directory = abspath(getcwd())
            chdir(self.TEMP_DIRECTORY)
            self._run(["docker", "compose"] + docker_args + args)
            if args == ["down"]:
                self._run(["docker", "compose", "rm", "-s", "-v", "-f"])
            chdir(starting_directory)

    def get_semaphore_updates(self):
        container_name = f"{self._get_compose_project_name()}_semaphore"
        try:
            container_info = self._run(["docker", "inspect", container_name])
            if f"Error: No such object: {container_name}" in container_info:
                raise Exception()
            container_info = loads(container_info)
        except Exception as e:
            raise SystemError(
                f"Semaphore container with name {container_name} could not be found"
            )
        response = self._run(
            [
                "docker",
                "exec",
                container_name,
                "/bin/sh",
                "/deployment/entrypoint.sh",
                "respond",
            ]
        )
        if response is None:
            response = []
        else:
            response = [r for r in response.split("\n") if len(r) > 0]
        return response

    def update_from_semaphore(self):
        try:
            semaphore = self.get_semaphore_updates()
        except SystemError:
            semaphore = []
        if len(semaphore) <= 0:
            return None
        all_containers = self._run(
            [
                "docker",
                "container",
                "list",
                "--no-trunc",
                "--all",
                "-f",
                "name=^deployment_.+$",
                "--format",
                "{{.Names}} ||| {{.Image}}",
            ]
        )
        containers_to_rebuild = []
        images_to_pull = []
        for container in all_containers.split("\n"):
            if len(container) <= 0:
                continue
            container_name, container_image = tuple(container.split(" ||| "))
            if container_image in semaphore or container_name in semaphore:
                containers_to_rebuild.append(container_name)
                images_to_pull.append(container_image)
        for image in images_to_pull:
            self._run(["docker", "pull", image])
        for container in containers_to_rebuild:
            self._run(["docker", "container", "stop", container])
            self._run(["docker", "container", "rm", container, "-v"])
        self.docker_compose("up")
        return containers_to_rebuild

    def registry_create_password(self, usr, pw, *args, **kwargs):
        self.docker_compose("up")
        compose_name = self._get_compose_project_name()
        docker = ["docker", "exec", f"{compose_name}_registry"]
        auth_path = "auth/registry.password"
        self._run(docker + ["apk", "add", "apache2-utils"])
        self._run(docker + ["htpasswd", "-B", "-b", "-c", auth_path, usr, pw])

    def certbot_new_domain(self, domain, email, *args, **kwargs):
        self.docker_compose("up")
        compose_name = self._get_compose_project_name()
        docker = ["docker", "exec", f"{compose_name}_certbot"]
        try:
            self._run(docker + ["rm", "-rf", f"/etc/letsencrypt/live/{domain}"])
        except subprocess.CalledProcessError:
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
        self.docker_compose("reload")

    def get_docker_volumes(self) -> list[str]:
        return [
            v
            for v in self._run(["docker", "volume", "ls", "-q"]).split("\n")
            if v.startswith(self._get_compose_project_name() + "_")
        ]

    def schedule_background_update(
        self, interval_minutes: Union[str, int, float], *args, **kwargs
    ):
        last_update = 0
        interval_minutes = float(interval_minutes)
        while True:
            if interval_minutes < 0 or time() - last_update > interval_minutes * 60:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    last_update = time()
                    updated_containers = self.update_from_semaphore()
                    if updated_containers is None:
                        print(timestamp, "No update")
                    else:
                        print(timestamp, "Updated: " + ", ".join(updated_containers))
                except KeyboardInterrupt:
                    return
                except Exception as e:
                    print(timestamp, "Error:", str(e))
            if interval_minutes < 0:
                break
            else:
                sleep(2.5)

    @property
    def _docker_compose_args(self) -> List[str]:
        args_attr = "_docker_compose_args_cached"
        if hasattr(self, args_attr):
            return self.__getattribute__(args_attr)
        self._generate_temp_directory()
        compose_args = []
        compose_files = []
        for root, dirs, files in walk(self.TEMP_DIRECTORY):
            for file in files:
                file_path = join(root, file)
                if not file.startswith("docker-compose.") or not file.endswith(".yml"):
                    continue
                compose_files.append(file_path)
        for file in sorted(compose_files, key=lambda f: len(f)):
            compose_args.append("-f")
            compose_args.append(abspath(file))
        compose_args += ["--env-file", self.ENV_PATH]
        self.__setattr__(args_attr, compose_args)
        return self._docker_compose_args


if __name__ == "__main__":
    handler = CmdHandler()
    chdir(handler.ROOT_DIRECTORY)
    argv = list(argv)
    if len(argv) < 2:
        argv.append("available_commands")
        if not hasattr(CmdHandler, argv[1]):
            raise ValueError("No argument passed to command script")
    argv[1] = argv[1].replace("-", "_")
    if not (hasattr(CmdHandler, argv[1]) and callable(getattr(CmdHandler, argv[1]))):
        raise ValueError(f"The requested command {argv[1]} was not found")
    if not isfile(handler.ENV_PATH):
        copyfile(handler.DEFAULT_ENV_PATH, handler.ENV_PATH)
    result = getattr(CmdHandler(), argv[1])(*argv[2:])
    print(f"{argv[1]} completed{': ' + str(result) if result else ''}")
