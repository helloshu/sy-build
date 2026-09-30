#!/usr/bin/env python3
"""Resolve a version-matched Android commit, including untagged prereleases."""
import argparse
import re
import subprocess
import sys
import tempfile


def git(*args, cwd=None, check=True):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def resolve(version, repository):
    if not re.fullmatch(r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        raise ValueError(f"Invalid upstream version: {version}")
    expected = version.removeprefix("v")
    tag = "refs/tags/v" + expected
    remote = git("ls-remote", "--exit-code", "--tags", repository, tag, check=False)
    if remote.returncode not in (0, 2):
        raise RuntimeError(f"Cannot query Android tags: {remote.stderr.strip()}")
    ref = tag if remote.returncode == 0 else "HEAD"
    with tempfile.TemporaryDirectory(prefix="sy-android-ref-") as directory:
        git("init", "-q", directory)
        git("remote", "add", "origin", repository, cwd=directory)
        git("fetch", "--depth=1", "--filter=blob:none", "origin", ref, cwd=directory)
        commit = git("rev-parse", "FETCH_HEAD^{commit}", cwd=directory).stdout.strip()
        gradle = git("show", f"{commit}:build.gradle", cwd=directory).stdout
        versions = re.findall(
            r"(?m)^[ \t]*(?:def[ \t]+)?siyuanVersionName[ \t]*=[ \t]*(['\"])([^'\"\r\n]+)\1[ \t]*(?://[^\r\n]*)?\r?$",
            gradle,
        )
        if len(versions) != 1 or versions[0][1] != expected:
            found = [value for _, value in versions]
            raise ValueError(
                f"Android {ref} version mismatch: expected {expected}, found {found}. "
                "A matching Android tag or default-branch version is required."
            )
        print(f"Android {version}: {ref} -> {commit}", file=sys.stderr)
        return commit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--repository", default="https://github.com/siyuan-note/siyuan-android.git")
    args = parser.parse_args()
    try:
        print(resolve(args.version, args.repository))
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
