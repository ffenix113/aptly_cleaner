import configobj
import StringIO
from validate import Validator


class Config(object):
    _def_conf = '''
    [repo_info]
    aptly_url = string(default='http://localhost:8081/api')
    run_user = string(default=None)
    search_dirs = list()
    [repos]
        [[__many__]]
        days_to_live = integer(min=5)
        max_packages = integer(min=5)
        priority = integer(min=0, max=1000)
        reference_only = boolean(default=False)
        distribution = string(default='wheezy')
        repo_list = list()
    '''

    def __init__(self, conf_path):
        self._path = conf_path
        def_conf = configobj.ConfigObj(configspec=StringIO.StringIO(Config._def_conf), interpolation=False)

        try:
            def_conf.merge(configobj.ConfigObj(conf_path, interpolation=False))
        except configobj.ConfigObjError:
            raise

        validator = Validator()
        vres = def_conf.validate(validator, preserve_errors=True)

        for (section, key, error) in configobj.flatten_errors(def_conf, vres):

            if error:
                message = "%s/%s: %s" % (
                    "/".join(section), key, error)
                raise configobj.ConfigObjError(message)

        self.conf = def_conf
        self.repos = def_conf['repos']

        self._cache = {
            'statuses': list()
        }

    # def get_aptly_url(self):
    #     return self.conf['repo_info']['aptly_url']

    def get_run_user(self):
        return self.conf['repo_info']['run_user']

    def get_glob_search_dirs(self):
        return self.conf['repo_info']['search_dirs']

    def get_statuses(self):
        """
        Get/create list of statuses sorted by their priority
        Higher priority == earlier in list
        :return:  Tuple (priority, status)
        """
        if not self._cache['statuses']:
            self._cache['statuses'] = [(self.get_param_by_status(st, 'priority'), st) for st in self.repos.keys()]
            self._cache['statuses'].sort(reverse=True)

        return self._cache['statuses']

    def get_param_by_status(self, status, param):
        try:
            return self._cache[status + "." + param]
        except KeyError:
            if status not in self.repos:
                raise KeyError('"{0}" not in repo statuses'.format(status))

            if param not in self.repos[status]:
                raise KeyError('Param "{0}" not in repo params'.format(param))

            self._cache[status + "." + param] = self.repos[status][param]
            return self._cache[status + "." + param]

    def get_days_to_live(self, status):
        return self.get_param_by_status(status, 'days_to_live')

    def get_max_packages(self, status):
        return self.get_param_by_status(status, 'max_packages')

    def get_repos_by_status(self, status):
        if status not in self.repos:
            raise KeyError('"{0}" not in repo statuses'.format(status))
        return self.repos[status]['repo_list']

    def get_repos_all(self):
        """
        Get all repos sorted by priority
        :return: Sorted repos by priority. tuple (priority, status, repos(list))
        """
        for priority, status in self.get_statuses():
            yield (priority, status, self.get_repos_by_status(status))
