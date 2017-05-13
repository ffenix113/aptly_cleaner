import argparse
import os
import glob
import subprocess
import math
from time import time, strftime
import config


class AptCleaner(object):
    def __init__(self, config_file, verbose, dry_run, only_repo, calc):
        self._verbose = bool(verbose)
        self.conf = config.Config(config_file)

        self._calc = calc
        self._saved = 0.0
        self._dry_run = dry_run or calc
        self._not_only_repo = not only_repo

        self._tmp_suffix = "_tmp"

        self._cache = {}
        self._init()

        self._check_time = time()

    def _init(self):
        # {
        #     repo_name: {
        #         package_name: (arch, versions[])
        #     }
        # }
        for _, status in self.conf.get_statuses():
            for repo in self.conf.get_repos_by_status(status):
                self._cache[repo] = {}

        if self._dry_run:
            self._verbose_message("dry-run is active, will not delete anything", True)

    def outdated(self, package_time, repo_status):
        return math.floor((self._check_time - package_time)/60/60/24) > self.conf.get_param_by_status(repo_status,
                                                                                                      'days_to_live')

    def _less_than_max(self, cnt, repo_status):
        return cnt <= self.conf.get_param_by_status(repo_status, 'max_packages')

    def _version_from_name(self, name):
        # TODO: Replace with regexp maybe?
        if name.endswith(")"):  # name for aptly. ex: 'google-chrome-stable (= 50.0.0)'
            return name.split("(= ")[1][:-1]

        # Ordinary name(or path). ex: '/data/uploads/google-chrome-stable_50.0.0_amd64.deb'
        name = name.split("/")[-1]
        return name.split("_")[-2]

    # TODO: Ask for rule
    def not_matches_rules(self, from_status, from_repo, package, version, modif_time):
        """
        Return bool whether package is valid for removal
        :param from_status: Repo status
        :param from_repo: skip check if current validating repo == from_repo
        :param package: Package name
        :param version: Version of package that is used
        :param modif_time: Time of last modification in seconds
        :return: True if package can be removed. False otherwise
        """

        if not self.outdated(modif_time, from_status):
            return False

        stats_list = self.conf.get_statuses()
        curr_priority = self.conf.get_param_by_status(from_status, 'priority')

        for priority, status in stats_list:
            if curr_priority >= priority:  # Do not match current status
                break

            for repo in self.conf.get_repos_by_status(status):
                if repo == from_repo and curr_priority == priority:
                    continue

                if package not in self._cache[repo]:
                    continue

                if version in self._cache[repo][package][1]:
                    self._verbose_message("[%s] %s %s (%s) %s %s %s %s" % (self.not_matches_rules.__name__, "package",
                                          package, version, "from", from_repo, "matched in", repo))
                    return False
        return True

    def _remove_file_from_fs(self, package):
        """
        Remove files from FS by name(abs path)
        :param package: Path to package that should be deleted. Must be absolute(in terms of this class)
        :return: None, pass on error
        """
        if self._verbose:
            self._verbose_message("[%s] %s %s" % (self._remove_file_from_fs.__name__, "removed from fs", package))

        if self._dry_run:
            return

        try:
            os.remove(package)
        except OSError:
            self._verbose_message("[%s] %s %s" % (self._remove_file_from_fs.__name__,
                                                  "failed to remove from fs:", package), True)

    def _remove_package_from_repo(self, repo, package_name, package_version):
        if self._verbose:
            self._verbose_message("[%s] %s %s, %s (%s)" % (self._remove_package_from_repo.__name__,
                                                           "repo remove", repo, package_name, package_version))
        package = "{0} (= {1})".format(package_name, package_version)
        # self._verbose_message("got version of package %s: %s" % (package_name, package_version))
        self._cache[repo][package_name][1].remove(package_version)
        if not self._dry_run:
            subprocess.call(['aptly', 'repo', 'remove', repo, "'{0}'".format(package)])

    def remove_package(self, package_name, package_file, repo):
        package_version = self._version_from_name(package_file)
        self._remove_package_from_repo(repo, package_name, package_version)
        if self._not_only_repo:
            self._remove_file_from_fs(package_file)

    def get_packages_in_dir(self, search_dir, package_format, versions, deep_scan=True):
        """
        Get files on FS in dir, with package_name
        :param search_dir: Directory to 'scan'
        :param package_format: Name of package to search for. Should contain placeholder for version
        :param versions: List of versions in order
        :param deep_scan: If false - search only in dir/, else in dir/*/ also
        :return: Generator, items as tuple (file_path, last_edit_time)
        """

        for version in versions:
            try:
                pckg_file = os.path.join(search_dir, package_format).format(version) + ".deb"
                yield pckg_file, os.stat(pckg_file).st_mtime
            except OSError:
                pass
            if deep_scan:
                for pckg_file in glob.iglob(os.path.join(search_dir, '*', package_format).format(version) + ".deb"):
                    yield (pckg_file, os.stat(pckg_file).st_mtime)

    def generate_package_cache(self, repo):
        if self._cache[repo]:
            self._verbose_message("cache is already generated for repo %s" % repo)
            return

        self._verbose_message("generating package cache for repo %s" % repo)
        # Using 'Name' to search for all valid packages. As per https://www.aptly.info/doc/feature/query/
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
                self._cache[repo][packg] = (arch, versions)

                packg, arch = raw_pack[0], raw_pack[2]
                versions = []

            versions.append(raw_pack[1])
        self._cache[repo][packg] = (arch, versions)

    def walk_packages_in_repo(self, repo):
        """
        Get all number of packages in repo
        :param repo: Repo to check
        :return: dict { package_name: count }, None if only_cache=True
        """
        self.generate_package_cache(repo)
        for package, info in self._cache[repo].iteritems():
            arch = info[0]
            versions = info[1]
            yield package, arch, len(versions), versions

    # Not yet polished so good. May(and probably will) fail miserably.
    def publish(self, distr, repo):
        if distr:
            repo = ("{0}-{1}" if not repo.startswith(distr + '-') else "{0} {1}").format(distr, repo)

        self._verbose_message("[%s] %s %s" % (self.publish.__name__, "publishing repo", repo))
        if self._dry_run:
            return

        subprocess.call(['aptly', 'publish', 'update', repo])

    def db_cleanup(self):
        if self._verbose:
            self._verbose_message("[%s] %s" % (self.db_cleanup.__name__, "db cleanup"))

        if self._dry_run:
            return
        try:
            subprocess.check_output(['aptly', 'db', 'cleanup', '-verbose'])
        except:
            self._verbose_message("[%s] %s" % (self.db_cleanup.__name__, "failed to cleanup"))

    def do_all_clean(self):

        # gen cache first, than do a cleanup
        for _, status in self.conf.get_statuses():
            # get repos from status
            for repo in self.conf.get_repos_by_status(status):
                self.generate_package_cache(repo)

        # get priority and statuses
        for _, status in self.conf.get_statuses():
            # Do not do cleanup if status is marked as 'reference_only'
            # reference_only statuses are used to do only rule matching
            if self.conf.get_param_by_status(status, 'reference_only'):
                self._verbose_message("{0} status is reference only, gen cache & skipping cleanup".format(status))
                # continue

            # get repos from status
            for repo in self.conf.get_repos_by_status(status):
                # self.__tmp_copy_repo(repo)
                if self.conf.get_param_by_status(status, 'reference_only'):
                    continue
                # get packages in repo
                for package, arch, count, versions in self.walk_packages_in_repo(repo):
                    # if len(versions) > max_count for repo - go for FS search
                    if self._less_than_max(count, status):
                        continue

                    package_format = "_".join([package, "{0}", arch])
                    for search_dir in self.conf.get_glob_search_dirs():
                        # search only for versions that are not greater than last possible
                        for pckg_file, modif_time in self.get_packages_in_dir(search_dir,
                                                                              package_format,
                                                                              versions[:-self.conf.get_max_packages(
                                                                                  status)]):
                            # print "[{0}][{1}]".format(status, repo), pckg_file, self.outdated(modif_time, status)
                            if self.not_matches_rules(status, repo, package,
                                                      self._version_from_name(pckg_file), modif_time):
                                if self._calc:
                                    self._saved += os.stat(pckg_file).st_size / 1024 / 1024
                                self.remove_package(package,
                                                    pckg_file,
                                                    repo)
                self.publish(self.conf.get_param_by_status(status, 'distribution'), repo)
                # self.__tmp_drop_repo(repo)
                self._verbose_message("-" * 20)
        self.db_cleanup()

        size = "MBs"
        if self._saved > 1024.0:
            self._saved /= 1024
            size = "GBs"

        self._verbose_message("[{0}] {1}".format('do_all', 'overall spoiled: %.3f %s' % (self._saved, size)), True)

    def _verbose_message(self, text, force=False):
        if not self._verbose and not force:
            return

        print strftime("[%Y/%m/%d %H:%M:%S]"), text

if __name__ == '__main__':
    # TODO: Also remove deps for removed packages?
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True, type=str, help='Path to config file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbosity')
    parser.add_argument('--dry-run', action='store_true', help="Don't actually remove packages")
    parser.add_argument('-r', '--only-from-repo', action='store_true', help="Remove packages only from repo, not FS")
    parser.add_argument('--calc', action='store_true', default=False, help="This option will calculate saved size" +
                        "Forces --dry-run, so will not actually delete anything")
    parser.add_argument('--force-invalid-user', action='store_true', default=False,
                        help='Use invalid user(not that specified in config) for running this script')

    args = parser.parse_args()
    cleaner = AptCleaner(args.config, args.verbose, args.dry_run, args.only_from_repo, args.calc)

    import getpass
    # Hardcoded as not needed to be configured as much
    if getpass.getuser() != cleaner.conf.get_run_user() and not args.force_invalid_user:
        raise EnvironmentError("Invalid user! To minimise damage current user cannot run this script.\n"
                               "Use --force-invalid-user if you want to force run with current user")

    cleaner.do_all_clean()
