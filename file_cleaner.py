import argparse
import os
import glob
import subprocess
from time import strftime

import config


class FileFinder(object):

    def __init__(self, config_file, dry_run, remove, verbose):
        self.conf = config.Config(config_file)

        self._not_dry_run = not dry_run
        self._remove = remove
        self._cache = dict()

        self._package_cache = set()

        self._verbose = verbose

    def _remove_file_from_fs(self, package):
        """
        Remove files from FS by name(abs path)
        :param package: Path to package that should be deleted. Must be absolute(in terms of this class)
        :return: None, pass on error
        """
        if self._verbose:
            self._verbose_message("[%s] %s %s" % (self._remove_file_from_fs.__name__, "removed from fs", package))

        try:
            os.remove(package)
        except OSError:
            self._verbose_message("[%s] %s %s" % (self._remove_file_from_fs.__name__,
                                                  "failed to remove from fs:", package), True)

    def generate_package_cache(self, repo):

        self._verbose_message("generating package cache for repo %s" % repo)

        repo_lines = str(subprocess.check_output(
            "aptly repo search " + repo + " 'Name' | sort -V", shell=True))

        repo_lines = repo_lines.splitlines()
        if len(repo_lines) < 1:
            raise ValueError('invalid response: {0}'.format(repo_lines))
        # Set default name
        packg = repo_lines[0].split("_")[0]
        versions = []
        arch = repo_lines[0].split("_")[2]
        for line in repo_lines:
            raw_pack = line.split("_")

            if raw_pack[0] != packg:
                if packg not in self._cache:
                    self._cache[packg] = list()
                self._cache[packg].append((arch, versions, repo))

                packg, arch = raw_pack[0], raw_pack[2]
                versions = []

            versions.append(raw_pack[1])

        if packg not in self._cache:
            self._cache[packg] = list()

        self._cache[packg].append((arch, versions, repo))

    def get_packages_in_dir(self, search_dir, deep_scan=True):
        """
        Get files on FS in dir, with package_name
        :param search_dir: Directory to 'scan'
        :param deep_scan: If false - search only in dir/*.deb, else in dir/*/*.deb also
        :return: None, set package cache
        """

        for pckg_file in glob.iglob(os.path.join(search_dir, '*') + ".deb"):
            self._package_cache.add(pckg_file)

        if deep_scan:
            for pckg_file in glob.iglob(os.path.join(search_dir, '*', '*') + ".deb"):
                self._package_cache.add(pckg_file)

    def is_in_cache(self, package_path):
        _package_splitted = package_path.split('/')[-1].split('_')
        package_name, package_version = _package_splitted[0], _package_splitted[1]

        if package_name in self._cache:
            for part in self._cache[package_name]:
                if package_version in part[1]:
                    return True
        return False

    def do_all(self):
        # gen cache first, than do a search
        for _, status in self.conf.get_statuses():
            # get repos from status
            for repo in self.conf.get_repos_by_status(status):
                self.generate_package_cache(repo)

        for search_dir in self.conf.get_glob_search_dirs():
            self.get_packages_in_dir(search_dir)

        # get priority and statuses
        mb_spoiled = 0.0
        for package_path in self._package_cache:
            # get repos from status
            if not self.is_in_cache(package_path):
                mb_spoiled += os.stat(package_path).st_size / 1024 / 1024
                self._verbose_message("[{0}] {1}".format('do_all/is_in_cache',
                                                         'package ' + package_path + ' is not in cache'))
                if self._not_dry_run and self._remove:
                    self._remove_file_from_fs(package_path)

        size = "MBs"
        if mb_spoiled > 1024.0:
            mb_spoiled /= 1024
            size = "GBs"
        self._verbose_message("[{0}] {1}".format('do_all', 'overall spoiled: %.3f %s' % (mb_spoiled, size)), True)

    def _verbose_message(self, text, force=False):
        if not self._verbose and not force:
            return

        print strftime("[%Y/%m/%d %H:%M:%S]"), text


def main(args):
    finder = FileFinder(args.config, args.dry_run, args.remove, args.verbose)
    finder.do_all()

    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True, help="Path to config")
    parser.add_argument('-v', '--verbose', action='store_true', default=False, help='Enable verbosity')
    parser.add_argument('-r', '--remove', action='store_true', default=False,
                        help='Remove all packages that are not in repos')
    parser.add_argument('--dry-run', action='store_true', default=False, help="Don't actually remove packages")

    main(parser.parse_args())
