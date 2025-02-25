#!/usr/bin/env python
#coding:utf-8
# +-------------------------------------------------------------------
# | 宝塔Linux面板
# +-------------------------------------------------------------------
# | Copyright (c) 2015-2016 宝塔软件(http://bt.cn) All rights reserved.
# +-------------------------------------------------------------------
# | Author: hwliang <hwl@bt.cn>
# +-------------------------------------------------------------------
import sys
import os
import public
import time
import json
import pwd
import cgi
import shutil
import re
import sqlite3
from BTPanel import session, request


class files:
    run_path = None
    path_permission_list = list()
    path_permission_exclude_list = list()
    file_permission_list = list()
    sqlite_connection = None
    download_list = None
    download_is_rm = None
    #检查敏感目录
    def CheckDir(self,path):
        path = path.replace('//','/')
        if path[-1:] == '/':
            path = path[:-1]
        
        nDirs = ('',
                 '/',
                '/*',
                '/www',
                '/root',
                '/boot',
                '/bin',
                '/etc',
                '/home',
                '/dev',
                '/sbin',
                '/var',
                '/usr', 
                '/tmp',
                '/sys',
                '/proc',
                '/media',
                '/mnt',
                '/opt',
                '/lib',
                '/srv', 
                '/selinux',
                '/www/server',
                '/www/server/data',
                public.GetConfigValue('logs_path'),
                public.GetConfigValue('setup_path'))

        return not path in nDirs

    # 网站文件操作前置检测
    def site_path_check(self, get):
        try:
            if not 'site_id' in get:
                return True
            if not self.run_path:
                self.run_path, self.path, self.site_name = self.GetSiteRunPath(
                    get.site_id)
            if 'path' in get:
                if get.path.find(self.path) != 0:
                    return False
            if 'sfile' in get:
                if get.sfile.find(self.path) != 0:
                    return False
            if 'dfile' in get:
                if get.dfile.find(self.path) != 0:
                    return False
            return True
        except:
            return True

    # 网站目录后续安全处理
    def site_path_safe(self, get):
        try:
            if not 'site_id' in get:
                return True
            run_path, path, site_name = self.GetSiteRunPath(get.site_id)
            if not os.path.exists(run_path):
                os.makedirs(run_path)
            ini_path = run_path + '/.user.ini'
            if os.path.exists(ini_path):
                return True
            sess_path = '/www/php_session/%s' % site_name
            if not os.path.exists(sess_path):
                os.makedirs(sess_path)
            ini_conf = '''open_basedir={}/:/tmp/:/proc/:{}/
session.save_path={}/
session.save_handler = files'''.format(path, sess_path, sess_path)
            public.writeFile(ini_path, ini_conf)
            public.ExecShell("chmod 644 %s" % ini_path)
            public.ExecShell("chdir +i %s" % ini_path)
            return True
        except:
            return False

    # 取当站点前运行目录
    def GetSiteRunPath(self, site_id):
        try:
            find = public.M('sites').where(
                'id=?', (site_id,)).field('path,name').find()
            siteName = find['name']
            sitePath = find['path']
            if public.get_webserver() == 'nginx':
                filename = '/www/server/panel/vhost/nginx/' + siteName + '.conf'
                if os.path.exists(filename):
                    conf = public.readFile(filename)
                    rep = '\s*root\s+(.+);'
                    tmp1 = re.search(rep, conf)
                    if tmp1:
                        path = tmp1.groups()[0]
            else:
                filename = '/www/server/panel/vhost/apache/' + siteName + '.conf'
                if os.path.exists(filename):
                    conf = public.readFile(filename)
                    rep = '\s*DocumentRoot\s*"(.+)"\s*\n'
                    tmp1 = re.search(rep, conf)
                    if tmp1:
                        path = tmp1.groups()[0]
            return path, sitePath, siteName
        except:
            return sitePath, sitePath, siteName

    # 检测文件名
    def CheckFileName(self, filename):
        nots = ['\\', '&', '*', '|', ';', '"', "'", '<', '>']
        if filename.find('/') != -1:
            filename = filename.split('/')[-1]
        for n in nots:
            if n in filename:
                return False
        return True

    # 名称输出过滤
    def xssencode(self, text):
        list = ['<', '>']
        ret = []
        for i in text:
            if i in list:
                i = ''
            ret.append(i)
        str_convert = ''.join(ret)
        if sys.version_info[0] == 3:
            import html
            text2 = html.escape(str_convert, quote=True)
        else:
            text2 = cgi.escape(str_convert, quote=True)

        reps = {'&amp;':'&'}
        for rep in reps.keys():
            if text2.find(rep) != -1: text2 = text2.replace(rep,reps[rep])
        return text2

    # 名称输入系列化
    def xssdecode(self,text):
        try:
            cs = {"&quot":'"',"&#x27":"'"}
            for c in cs.keys():
                text = text.replace(c,cs[c])

            str_convert = text
            if sys.version_info[0] == 3:
                import html
                text2 = html.unescape(str_convert)
            else:
                text2 = cgi.unescape(str_convert)
            return text2
        except:
            return text

    # 上传文件
    def UploadFile(self, get):
        from werkzeug.utils import secure_filename
        from BTPanel import request
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        if not os.path.exists(get.path):
            os.makedirs(get.path)
        f = request.files['zunfile']
        filename = os.path.join(get.path, f.filename)
        if sys.version_info[0] == 2:
            filename = filename.encode('utf-8')
        s_path = get.path
        if os.path.exists(filename):
            s_path = filename
        p_stat = os.stat(s_path)
        f.save(filename)
        os.chown(filename, p_stat.st_uid, p_stat.st_gid)
        os.chmod(filename, p_stat.st_mode)
        public.WriteLog('TYPE_FILE', 'FILE_UPLOAD_SUCCESS',
                        (filename, get['path']))
        return public.returnMsg(True, 'FILE_UPLOAD_SUCCESS')

    def f_name_check(self,filename):
        '''
            @name 文件名检测2
            @author hwliang<2021-03-16>
            @param filename<string> 文件名
            @return bool
        '''
        f_strs = [';','&','<','>']
        for fs in f_strs:
            if filename.find(fs) != -1:
                return False
        return True


    # 上传文件2
    def upload(self, args):
        if not 'f_name' in args:
            args.f_name = request.form.get('f_name')
            args.f_path = request.form.get('f_path')
            args.f_size = request.form.get('f_size')
            args.f_start = request.form.get('f_start')

        if sys.version_info[0] == 2:
            args.f_name = args.f_name.encode('utf-8')
            args.f_path = args.f_path.encode('utf-8')


        if not self.f_name_check(args.f_name): return public.returnMsg(False,'FILE_NAME_ERR')

        if args.f_path == '/':
            return public.returnMsg(False,'UPLOAD_DIR_ERR')

        if args.f_name.find('./') != -1 or args.f_path.find('./') != -1:
            return public.returnMsg(False, 'WRONG_PARAMETER')
        if not os.path.exists(args.f_path):
            os.makedirs(args.f_path, 493)
            if not 'dir_mode' in args or not 'file_mode' in args:
                self.set_mode(args.f_path)

        save_path = os.path.join(
            args.f_path, args.f_name + '.' + str(int(args.f_size)) + '.upload.tmp')
        d_size = 0
        if os.path.exists(save_path):
            d_size = os.path.getsize(save_path)
        if d_size != int(args.f_start):
            return d_size
        f = open(save_path, 'ab')
        if 'b64_data' in args:
            import base64
            b64_data = base64.b64decode(args.b64_data)
            f.write(b64_data)
        else:
            upload_files = request.files.getlist("blob")
            for tmp_f in upload_files:
                f.write(tmp_f.read())
        f.close()
        f_size = os.path.getsize(save_path)
        if f_size != int(args.f_size):
            return f_size
        new_name = os.path.join(args.f_path, args.f_name)
        if os.path.exists(new_name):
            if new_name.find('.user.ini') != -1:
                public.ExecShell("chattr -i " + new_name)
            try:
                os.remove(new_name)
            except:
                public.ExecShell("rm -f %s" % new_name)
        os.renames(save_path, new_name)
        if 'dir_mode' in args and 'file_mode' in args:
            mode_tmp1 = args.dir_mode.split(',')
            public.set_mode(args.f_path, mode_tmp1[0])
            public.set_own(args.f_path, mode_tmp1[1])
            mode_tmp2 = args.file_mode.split(',')
            public.set_mode(new_name, mode_tmp2[0])
            public.set_own(new_name, mode_tmp2[1])

        else:
            self.set_mode(new_name)
        if new_name.find('.user.ini') != -1:
            public.ExecShell("chattr +i " + new_name)

        public.WriteLog('TYPE_FILE', 'FILE_UPLOAD_SUCCESS',
                        (args.f_name, args.f_path))
        return public.returnMsg(True, 'FILE_UPLOAD_SUCCESS')

    # 设置文件和目录权限
    def set_mode(self, path):
        s_path = os.path.dirname(path)
        p_stat = os.stat(s_path)
        os.chown(path,p_stat.st_uid,p_stat.st_gid)
        if os.path.isfile(path):
            os.chmod(path, 0o644)
        else:
            os.chmod(path,p_stat.st_mode)

    # 是否包含composer.json
    def is_composer_json(self,path):
        if os.path.exists(path + '/composer.json'):
            return '1'
        return '0'

    def __check_favorite(self,filepath,favorites_info):
        for favorite in favorites_info:
            if filepath == favorite['path']:
                return '1'
        return '0'

    def __check_share(self,filename):
        my_table = 'download_token'
        result = public.M(my_table).where('filename=?',(filename,)).getField('id')
        if result:
            return str(result)
        return '0'


    def __filename_flater(self,filename):
        ms = {";":""}
        for m in ms.keys():
            filename = filename.replace(m,ms[m])
        return filename

    # 取文件/目录列表
    def GetDir(self, get):
        if not hasattr(get, 'path'):
            # return public.returnMsg(False,'错误的参数!')
            get.path = '/www/wwwroot'
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        if get.path == '':
            get.path = '/www'
        get.path = self.xssdecode(get.path)
        if not os.path.exists(get.path):
            get.path = '/www/wwwroot'
            #return public.ReturnMsg(False, '指定目录不存在!')
        if get.path == '/www/Recycle_bin':
            return public.returnMsg(False,'RECYCLE_BIN_ERR')
        if not os.path.isdir(get.path):
            get.path = os.path.dirname(get.path)

        if not os.path.isdir(get.path):
            return public.returnMsg(False,'DIR_ERR')

        import pwd
        dirnames = []
        filenames = []

        search = None
        if hasattr(get, 'search'):
            search = get.search.strip().lower()
        if hasattr(get, 'all'):
            return self.SearchFiles(get)

        # 包含分页类
        import page
        # 实例化分页类
        page = page.Page()
        info = {}
        info['count'] = self.GetFilesCount(get.path, search)
        info['row'] = 100
        if 'disk' in get:
            if get.disk == 'true': info['row'] = 2000
        if 'share' in get and get.share:
            info['row'] = 5000
        info['p'] = 1
        if hasattr(get, 'p'):
            try:
                info['p'] = int(get['p'])
            except:
                info['p'] = 1

        info['uri'] = {}
        info['return_js'] = ''
        if hasattr(get, 'tojs'):
            info['return_js'] = get.tojs
        if hasattr(get, 'showRow'):
            info['row'] = int(get.showRow)

        # 获取分页数据
        data = {}
        data['PAGE'] = page.GetPage(info, '1,2,3,4,5,6,7,8')

        i = 0
        n = 0

        data['STORE'] = self.get_files_store(None)
        data['FILE_RECYCLE'] = os.path.exists('data/recycle_bin.pl')

        if not hasattr(get, 'reverse'):
            for filename in os.listdir(get.path):
                filename = self.xssencode(filename)

                if search:
                    if filename.lower().find(search) == -1:
                        continue
                i += 1
                if n >= page.ROW:
                    break
                if i < page.SHIFT:
                    continue

                try:
                    if sys.version_info[0] == 2:
                        filename = filename.encode('utf-8')
                    else:
                        filename.encode('utf-8')
                    filePath = get.path+'/'+filename
                    link = ''
                    if os.path.islink(filePath):
                        filePath = os.readlink(filePath)
                        link = ' -> ' + filePath
                        if not os.path.exists(filePath):
                            filePath = get.path + '/' + filePath
                        if not os.path.exists(filePath):
                            continue
                    stat = os.stat(filePath)
                    accept = str(oct(stat.st_mode)[-3:])
                    mtime = str(int(stat.st_mtime))
                    user = ''
                    try:
                        user = pwd.getpwuid(stat.st_uid).pw_name
                    except:
                        user = str(stat.st_uid)
                    size = str(stat.st_size)
                    # 判断文件是否已经被收藏
                    favorite = self.__check_favorite(filePath,data['STORE'])
                    if os.path.isdir(filePath):
                        dirnames.append(self.__filename_flater(filename)+';'+size+';' + mtime+';'+accept+';'+user+';'+link + ';' +
                                        self.get_download_id(filePath)+';'+ self.is_composer_json(filePath)+';'
                                        +favorite+';'+self.__check_share(filePath))
                    else:
                        filenames.append(self.__filename_flater(filename)+';'+size+';'+mtime+';'+accept+';'+user+';'+link+';'
                                         +self.get_download_id(filePath)+';' + self.is_composer_json(filePath)+';'
                                         +favorite+';'+self.__check_share(filePath))
                    n += 1
                except:
                    continue

            data['DIR'] = sorted(dirnames)
            data['FILES'] = sorted(filenames)
        else:
            reverse = bool(get.reverse)
            if get.reverse == 'False':
                reverse = False
            for file_info in self.__list_dir(get.path, get.sort, reverse):
                filename = os.path.join(get.path, file_info[0])
                if search:
                    if file_info[0].lower().find(search) == -1:
                        continue
                i += 1
                if n >= page.ROW:
                    break
                if i < page.SHIFT:
                    continue
                if not os.path.exists(filename): continue
                file_info = self.__format_stat(filename, get.path)
                if not file_info: continue
                favorite = self.__check_favorite(filename, data['STORE'])
                r_file = self.__filename_flater(file_info['name']) + ';' + str(file_info['size']) + ';' + str(file_info['mtime']) + ';' + str(
                    file_info['accept']) + ';' + file_info['user'] + ';' + file_info['link']+';'\
                         + self.get_download_id(filename) + ';' + self.is_composer_json(filename)+';'\
                         + favorite+';'+self.__check_share(filename)
                if os.path.isdir(filename):
                    dirnames.append(r_file)
                else:
                    filenames.append(r_file)
                n += 1

            data['DIR'] = dirnames
            data['FILES'] = filenames
        data['PATH'] = str(get.path)
        for i in range(len(data['DIR'])):
            data['DIR'][i] += ';' + self.get_file_ps( os.path.join(data['PATH'] , data['DIR'][i].split(';')[0]))

        for i in range(len(data['FILES'])):
            data['FILES'][i] += ';' + self.get_file_ps( os.path.join(data['PATH'] , data['FILES'][i].split(';')[0]))

        if hasattr(get, 'disk'):
            import system
            data['DISK'] = system.system().GetDiskInfo()
        return data


    def get_file_ps(self,filename):
        '''
            @name 获取文件或目录备注
            @author hwliang<2020-10-22>
            @param filename<string> 文件或目录全路径
            @return string
        '''
        ps_path = '/www/server/panel/data/files_ps'
        f_key1 = '/'.join((ps_path,public.md5(filename)))
        if os.path.exists(f_key1):
            return public.readFile(f_key1)

        f_key2 = '/'.join((ps_path,public.md5(os.path.basename(filename))))
        if os.path.exists(f_key2):
            return public.readFile(f_key2)

        pss = {
            '/www/server/data':'MySQL data storage directory!',
            '/www/server/mysql':'MySQL program directory',
            '/www/server/redis':'Redis program directory',
            '/www/server/mongodb':'MongoDB program directory',
            '/www/server/nvm':'PM2/NVM/NPM program directory',
            '/www/server/pass':'Website Basic Auth authentication password storage directory',
            '/www/server/speed':'Website speed plugin directory',
            '/www/server/docker':'Docker and data directory',
            '/www/server/total':'Website Statistics Directory',
            '/www/server/btwaf':'WAF directory',
            '/www/server/pure-ftpd':'ftp program directory',
            '/www/server/phpmyadmin':'phpMyAdmin program directory',
            '/www/server/rar':'rar extension library directory, after deleting, it will lose support for RAR compressed files',
            '/www/server/stop':'Website disabled page directory, please do not delete!',
            '/www/server/nginx':'Nginx program directory',
            '/www/server/apache':'Apache program directory',
            '/www/server/cron':'Cron script and log directory',
            '/www/server/php':'All interpreters of PHP versions are in this directory',
            '/www/server/tomcat':'Tomcat program directory',
            '/www/php_session':'PHP-SESSION Quarantine directory'
        }
        if filename in pss:  return pss[filename]
        return ''


    def set_file_ps(self,args):
        '''
            @name 设置文件或目录备注
            @author hwliang<2020-10-22>
            @param filename<string> 文件或目录全路径
            @param ps_type<int> 备注类型 0.完整路径 1.文件名称
            @param ps_body<string> 备注内容
            @return dict
        '''
        filename = args.filename.strip()
        ps_type = int(args.ps_type)
        ps_body = public.xssencode(args.ps_body)
        ps_path = '/www/server/panel/data/files_ps'
        if not os.path.exists(ps_path):
            os.makedirs(ps_path,384)
        if ps_type == 1:
            f_name = os.path.basename(filename)
        else:
            f_name = filename
        ps_key = public.md5(f_name)

        f_key = '/'.join((ps_path,ps_key))
        if ps_body:
            public.writeFile(f_key,ps_body)
            public.WriteLog('TYPE_FILE','SET_FILE_NOTES',(f_name,ps_body))
        else:
            if os.path.exists(f_key):os.remove(f_key)
            public.WriteLog('TYPE_FILE','CLEAR_FILE_NOTES',(f_name))
        return public.returnMsg(True,'SET_SUCCESS')



    def check_file_sort(self,sort):
        """
        @校验排序字段
        """
        slist = ['name','size','mtime','accept','user']
        if sort in slist: return sort
        return 'name'

    def __list_dir(self, path, my_sort='name', reverse=False):
        '''
            @name 获取文件列表，并排序
            @author hwliang<2020-08-01>
            @param path<string> 路径
            @param my_sort<string> 排序字段
            @param reverse<bool> 是否降序
            @param list
        '''
        if not os.path.exists(path):
            return []
        py_v = sys.version_info[0]
        tmp_files = []

        for f_name in os.listdir(path):
            try:
                if py_v == 2:
                    f_name = f_name.encode('utf-8')
                else:
                    f_name.encode('utf-8')

                #使用.join拼接效率更高
                filename = "/".join((path,f_name))
                sort_key = 1
                sort_val = None

                #此处直接做异常处理比先判断文件是否存在更高效
                if my_sort == 'name':
                    sort_key = 0
                elif my_sort == 'size':
                    sort_val = os.stat(filename).st_size
                elif my_sort == 'mtime':
                    sort_val =  os.stat(filename).st_mtime
                elif my_sort == 'accept':
                    sort_val = os.stat(filename).st_mode
                elif my_sort == 'user':
                    sort_val =  os.stat(filename).st_uid
            except:
                continue
            #使用list[tuple]排序效率更高
            tmp_files.append((f_name,sort_val))
        try:
            tmp_files = sorted(tmp_files, key=lambda x: x[sort_key], reverse=reverse)
        except:pass
        return tmp_files

    def __format_stat(self, filename, path):
        try:
            stat = self.__get_stat(filename, path)
            if not stat:
                return None
            tmp_stat = stat.split(';')
            file_info = {'name': self.xssencode(tmp_stat[0].replace('/', '')), 'size': int(tmp_stat[1]), 'mtime': int(
                tmp_stat[2]), 'accept': int(tmp_stat[3]), 'user': tmp_stat[4], 'link': tmp_stat[5]}
            return file_info
        except:
            return None

    def SearchFiles(self, get):
        if not hasattr(get, 'path'):
            get.path = '/www/wwwroot'
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        if not os.path.exists(get.path):
            get.path = '/www'
        search = get.search.strip().lower()
        my_dirs = []
        my_files = []
        count = 0
        max = 3000
        for d_list in os.walk(get.path):
            if count >= max:
                break
            for d in d_list[1]:
                if count >= max:
                    break
                d = self.xssencode(d)
                if d.lower().find(search) != -1:
                    filename = d_list[0] + '/' + d
                    if not os.path.exists(filename):
                        continue
                    my_dirs.append(self.__get_stat(filename, get.path))
                    count += 1

            for f in d_list[2]:
                if count >= max:
                    break
                f = self.xssencode(f)
                if f.lower().find(search) != -1:
                    filename = d_list[0] + '/' + f
                    if not os.path.exists(filename):
                        continue
                    my_files.append(self.__get_stat(filename, get.path))
                    count += 1
        data = {}
        data['DIR'] = sorted(my_dirs)
        data['FILES'] = sorted(my_files)
        data['PATH'] = str(get.path)
        data['PAGE'] = public.get_page(
            len(my_dirs) + len(my_files), 1, max, 'GetFiles')['page']
        data['STORE'] = self.get_files_store(None)
        return data

    def __get_stat(self, filename, path=None):
        stat = os.stat(filename)
        accept = str(oct(stat.st_mode)[-3:])
        mtime = str(int(stat.st_mtime))
        user = ''
        try:
            user = pwd.getpwuid(stat.st_uid).pw_name
        except:
            user = str(stat.st_uid)
        size = str(stat.st_size)
        link = ''
        down_url = self.get_download_id(filename)
        if os.path.islink(filename):
            link = ' -> ' + os.readlink(filename)
        tmp_path = (path + '/').replace('//', '/')
        if path and tmp_path != '/':
            filename = filename.replace(tmp_path, '',1)
        favorite = self.__check_favorite(filename, self.get_files_store(None))
        return filename + ';' + size + ';' + mtime + ';' + accept + ';' + user + ';' + link+';'+ down_url+';'+ \
               self.is_composer_json(filename)+';'+favorite+';'+self.__check_share(filename)

    #获取指定目录下的所有视频或音频文件
    def get_videos(self,args):
        path = args.path.strip()
        v_data = []
        if not os.path.exists(path): return v_data
        import mimetypes
        for fname in os.listdir(path):
            try:
                filename = os.path.join(path,fname)
                if not os.path.exists(filename): continue
                if not os.path.isfile(filename): continue
                v_tmp = {}
                v_tmp['name'] = fname
                v_tmp['type'] = mimetypes.guess_type(filename)[0]
                v_tmp['size'] = os.path.getsize(filename)
                if not v_tmp['type'].split('/')[0] in ['video']:
                    continue
                v_data.append(v_tmp)
            except:continue
        return sorted(v_data,key=lambda x:x['name'])

    # 计算文件数量
    def GetFilesCount(self, path, search):
        if os.path.isfile(path):
            return 1
        if not os.path.exists(path):
            return 0
        i = 0
        for name in os.listdir(path):
            if search:
                if name.lower().find(search) == -1:
                    continue
            i += 1
        return i

    # 创建文件
    def CreateFile(self, get):
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8').strip()
        try:
            if get.path[-1] == '.':
                return public.returnMsg(False, 'File_END_WITH')
            if not self.CheckFileName(get.path):
                return public.returnMsg(False, 'FILE_NAME_SPECIAL_CHARACTRES')
            if os.path.exists(get.path):
                return public.returnMsg(False, 'FILE_EXISTS')
            path = os.path.dirname(get.path)
            if not os.path.exists(path):
                os.makedirs(path)
            open(get.path, 'w+').close()
            self.SetFileAccept(get.path)
            public.WriteLog('TYPE_FILE', 'FILE_CREATE_SUCCESS', (get.path,))
            return public.returnMsg(True, 'FILE_CREATE_SUCCESS')
        except:
            return public.returnMsg(False, 'FILE_CREATE_ERR')

    #创建软链
    def CreateLink(self,get):
        '''
            @name 创建软链接
            @author hwliang<2021-03-23>
            @param get<dict_obj{
                sfile<string> 源文件
                dfile<string> 软链文件名
            }>
            @return dict
        '''

        if not 'sfile' in get: return public.returnMsg(False,'INIT_ARGS_ERR')
        if not os.path.exists(get.sfile): return public.returnMsg(False,'FILE_NOT_EXISTS')
        if os.path.exists(get.dfile): return public.returnMsg(False,'SOFTCHAIN_FILE_EXIST')
        if get.dfile[0] != '/': return public.returnMsg(False,'SOFTCHAIN_FILE_PATH')
        public.ExecShell("ln -sf {} {}".format(get.sfile,get.dfile))
        if not os.path.exists(get.dfile): return public.returnMsg(False,'SOFTLINK_CREATE_ERR')
        public.WriteLog('TYPE_FIREWALL','CREATE_SOFTLINK',(get.dfile,get.sfile))
        return public.returnMsg(True,'SOFTLINK_CREATE_SUCCESS')



    # 创建目录
    def CreateDir(self, get):
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8').strip()
        try:
            if get.path[-1] == '.':
                return public.returnMsg(False, 'DIR_END_WITH1')
            if not self.CheckFileName(get.path):
                return public.returnMsg(False, 'DIR_NAME_SPECIAL_CHARACTRES')
            if os.path.exists(get.path):
                return public.returnMsg(False, 'DIR_EXISTS')
            os.makedirs(get.path)
            self.SetFileAccept(get.path)
            public.WriteLog('TYPE_FILE', 'DIR_CREATE_SUCCESS', (get.path,))
            return public.returnMsg(True, 'DIR_CREATE_SUCCESS')
        except:
            return public.returnMsg(False,'DIR_CREATE_ERR')

    #删除目录
    def DeleteDir(self,get):
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        if get.path == '/www/Recycle_bin':
            return public.returnMsg(False,'RECYCLE_BIN_ERR')
        if not os.path.exists(get.path):
            return public.returnMsg(False, 'DIR_NOT_EXISTS')

        # 检查是否敏感目录
        if not self.CheckDir(get.path):
            return public.returnMsg(False, 'FILE_DANGER')

        try:
            # 检查是否存在.user.ini
            # if os.path.exists(get.path+'/.user.ini'):
            #    public.ExecShell("chattr -i '"+get.path+"/.user.ini'")
            public.ExecShell("chattr -R -i " + get.path)
            if hasattr(get, 'empty'):
                if not self.delete_empty(get.path):
                    return public.returnMsg(False, 'DIR_ERR_NOT_EMPTY')

            if os.path.exists('data/recycle_bin.pl') and session.get('debug') != 1:
                if self.Mv_Recycle_bin(get):
                    self.site_path_safe(get)
                    return public.returnMsg(True, 'DIR_MOVE_RECYCLE_BIN')

            import shutil
            shutil.rmtree(get.path)
            self.site_path_safe(get)
            public.WriteLog('TYPE_FILE', 'DIR_DEL_SUCCESS', (get.path,))
            return public.returnMsg(True, 'DIR_DEL_SUCCESS')
        except:
            return public.returnMsg(False, 'DIR_DEL_ERR')

    # 删除 空目录
    def delete_empty(self, path):
        if sys.version_info[0] == 2:
            path = path.encode('utf-8')
        if len(os.listdir(path)) > 0:
            return False
        return True

    # 删除文件
    def DeleteFile(self, get):
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        if not os.path.exists(get.path):
            return public.returnMsg(False, 'FILE_NOT_EXISTS')

        # 检查是否为.user.ini
        if get.path.find('.user.ini') != -1:
            public.ExecShell("chattr -i '"+get.path+"'")
        try:
            if os.path.exists('data/recycle_bin.pl') and session.get('debug') != 1:
                if self.Mv_Recycle_bin(get):
                    self.site_path_safe(get)
                    return public.returnMsg(True, 'FILE_MOVE_RECYCLE_BIN')
            os.remove(get.path)
            self.site_path_safe(get)
            public.WriteLog('TYPE_FILE', 'FILE_DEL_SUCCESS', (get.path,))
            return public.returnMsg(True, 'FILE_DEL_SUCCESS')
        except:
            return public.returnMsg(False, 'FILE_DEL_ERR')

    # 移动到回收站
    def Mv_Recycle_bin(self, get):
        rPath = '/www/Recycle_bin/'
        if not os.path.exists(rPath):
            public.ExecShell('mkdir -p ' + rPath)
        rFile = rPath + \
            get.path.replace('/', '_bt_') + '_t_' + str(time.time())
        try:
            import shutil
            shutil.move(get.path, rFile)
            public.WriteLog('TYPE_FILE', 'FILE_MOVE_RECYCLE_BIN', (get.path,))
            return True
        except:
            public.WriteLog(
                'TYPE_FILE', 'FILE_MOVE_RECYCLE_BIN_ERR', (get.path,))
            return False

    # 从回收站恢复
    def Re_Recycle_bin(self, get):
        rPath = '/www/Recycle_bin/'
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        dFile = get.path.replace('_bt_', '/').split('_t_')[0]
        get.path = rPath + get.path
        if dFile.find('BTDB_') != -1:
            import database
            return database.database().RecycleDB(get.path)
        try:
            import shutil
            shutil.move(get.path, dFile)
            public.WriteLog('TYPE_FILE', 'FILE_RE_RECYCLE_BIN', (dFile,))
            return public.returnMsg(True, 'FILE_RE_RECYCLE_BIN')
        except:
            public.WriteLog('TYPE_FILE', 'FILE_RE_RECYCLE_BIN_ERR', (dFile,))
            return public.returnMsg(False, 'FILE_RE_RECYCLE_BIN_ERR')

    # 获取回收站信息
    def Get_Recycle_bin(self, get):
        rPath = '/www/Recycle_bin/'
        if not os.path.exists(rPath):
            public.ExecShell('mkdir -p ' + rPath)
        data = {}
        data['dirs'] = []
        data['files'] = []
        data['status'] = os.path.exists('data/recycle_bin.pl')
        data['status_db'] = os.path.exists('data/recycle_bin_db.pl')
        for file in os.listdir(rPath):
            file = self.xssencode(file)
            try:
                tmp = {}
                fname = rPath + file
                if sys.version_info[0] == 2:
                    fname = fname.encode('utf-8')
                else:
                    fname.encode('utf-8')
                tmp1 = file.split('_bt_')
                tmp2 = tmp1[len(tmp1)-1].split('_t_')
                tmp['rname'] = file
                tmp['dname'] = file.replace('_bt_', '/').split('_t_')[0]
                tmp['name'] = tmp2[0]
                tmp['time'] = int(float(tmp2[1]))
                if os.path.islink(fname):
                    filePath = os.readlink(fname)
                    if os.path.exists(filePath):
                        tmp['size'] = os.path.getsize(filePath)
                    else:
                        tmp['size'] = 0
                else:
                    tmp['size'] = os.path.getsize(fname)
                if os.path.isdir(fname):
                    data['dirs'].append(tmp)
                else:
                    data['files'].append(tmp)
            except:
                continue

        data['dirs'] = sorted(data['dirs'],key = lambda x: x['time'],reverse=True)
        data['files'] = sorted(data['files'],key = lambda x: x['time'],reverse=True)
        return data

    # 彻底删除
    def Del_Recycle_bin(self, get):
        rPath = '/www/Recycle_bin/'
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        dFile = get.path.split('_t_')[0]
        filename = rPath + get.path
        tfile = get.path.replace('_bt_', '/').split('_t_')[0]
        if not os.path.exists(filename):
            return public. returnMsg(True, 'FILE_DEL_RECYCLE_BIN', (tfile,))
        if dFile.find('BTDB_') != -1:
            import database
            return database.database().DeleteTo(filename)
        if not self.CheckDir(filename):
            return public.returnMsg(False, 'FILE_DANGER')

        public.ExecShell('chattr -R -i ' + filename)
        if os.path.isdir(filename):
            import shutil
            try:
                shutil.rmtree(filename)
            except:
                public.ExecShell("rm -rf " + filename)
        else:
            try:
                os.remove(filename)
            except:
                public.ExecShell("rm -f " + filename)
        public.WriteLog('TYPE_FILE', 'FILE_DEL_RECYCLE_BIN', (tfile,))
        return public.returnMsg(True, 'FILE_DEL_RECYCLE_BIN', (tfile,))

    # 清空回收站
    def Close_Recycle_bin(self, get):
        rPath = '/www/Recycle_bin/'
        public.ExecShell('chattr -R -i ' + rPath)
        import database
        import shutil
        rlist = os.listdir(rPath)
        i = 0
        l = len(rlist)
        for name in rlist:
            i += 1
            path = rPath + name
            public.writeSpeed(name, i, l)
            if name.find('BTDB_') != -1:
                database.database().DeleteTo(path)
                continue
            if os.path.isdir(path):
                try:
                    shutil.rmtree(path)
                except:
                    public.ExecShell('rm -rf ' + path)
            else:
                try:
                    os.remove(path)
                except:
                    public.ExecShell('rm -f ' + path)

        public.writeSpeed(None, 0, 0)
        public.WriteLog('TYPE_FILE', 'FILE_CLOSE_RECYCLE_BIN')
        return public.returnMsg(True, 'FILE_CLOSE_RECYCLE_BIN')

    # 回收站开关
    def Recycle_bin(self, get):
        c = 'data/recycle_bin.pl'
        if hasattr(get, 'db'):
            c = 'data/recycle_bin_db.pl'
        if os.path.exists(c):
            os.remove(c)
            public.WriteLog('TYPE_FILE', 'FILE_OFF_RECYCLE_BIN')
            return public.returnMsg(True, 'FILE_OFF_RECYCLE_BIN')
        else:
            public.writeFile(c, 'True')
            public.WriteLog('TYPE_FILE', 'FILE_ON_RECYCLE_BIN')
            return public.returnMsg(True, 'FILE_ON_RECYCLE_BIN')

    # 复制文件
    def CopyFile(self, get):
        if sys.version_info[0] == 2:
            get.sfile = get.sfile.encode('utf-8')
            get.dfile = get.dfile.encode('utf-8')
        if get.dfile[-1] == '.':
            return public.returnMsg(False, 'File_END_WITH')
        if not os.path.exists(get.sfile):
            return public.returnMsg(False, 'FILE_NOT_EXISTS')

        # if os.path.exists(get.dfile):
        #    return public.returnMsg(False,'FILE_EXISTS')

        if os.path.isdir(get.sfile):
            return self.CopyDir(get)

        import shutil
        try:
            shutil.copyfile(get.sfile, get.dfile)
            public.WriteLog('TYPE_FILE', 'FILE_COPY_SUCCESS',
                            (get.sfile, get.dfile))
            stat = os.stat(get.sfile)
            os.chmod(get.dfile,stat.st_mode)
            os.chown(get.dfile, stat.st_uid, stat.st_gid)
            return public.returnMsg(True, 'FILE_COPY_SUCCESS')
        except:
            return public.returnMsg(False, 'FILE_COPY_ERR')

    # 复制文件夹
    def CopyDir(self, get):
        if sys.version_info[0] == 2:
            get.sfile = get.sfile.encode('utf-8')
            get.dfile = get.dfile.encode('utf-8')
        if get.dfile[-1] == '.':
            return public.returnMsg(False, 'DIR_END_WITH1')
        if not os.path.exists(get.sfile):
            return public.returnMsg(False, 'DIR_NOT_EXISTS')

        # if os.path.exists(get.dfile):
        #    return public.returnMsg(False,'DIR_EXISTS')

        # if not self.CheckDir(get.dfile):
        #    return public.returnMsg(False,'FILE_DANGER')

        try:
            self.copytree(get.sfile, get.dfile)
            stat = os.stat(get.sfile)
            os.chmod(get.dfile,stat.st_mode)
            os.chown(get.dfile, stat.st_uid, stat.st_gid)
            public.WriteLog('TYPE_FILE', 'DIR_COPY_SUCCESS',
                            (get.sfile, get.dfile))
            return public.returnMsg(True, 'DIR_COPY_SUCCESS')
        except:
            return public.returnMsg(False, 'DIR_COPY_ERR')

    # 移动文件或目录
    def MvFile(self, get):
        if sys.version_info[0] == 2:
            get.sfile = get.sfile.encode('utf-8')
            get.dfile = get.dfile.encode('utf-8')
        if get.dfile[-1] == '.':
            return public.returnMsg(False, 'File_END_WITH')
        if not self.CheckFileName(get.dfile):
            return public.returnMsg(False,'FILE_NAME_SPECIAL_CHARACTRES')
        if get.sfile == '/www/Recycle_bin':
            return public.returnMsg(False,'RECYCLE_BIN_ERR')
        if not os.path.exists(get.sfile):
            return public.returnMsg(False, 'FILE_NOT_EXISTS')

        if os.path.exists(get.dfile):
            return public.returnMsg(False,'FILE_EXIST_ERR')

        if get.dfile[-1] == '/':
            get.dfile = get.dfile[:-1]

        if get.dfile == get.sfile:
            return public.returnMsg(False,'MEANINGLESS_OPERA')
        
        if not self.CheckDir(get.sfile):
            return public.returnMsg(False,'FILE_DANGER')
        try:
            self.move(get.sfile,get.dfile)
            self.site_path_safe(get)
            if hasattr(get,'rename'):
                public.WriteLog('TYPE_FILE','RENAME',(get.sfile,get.dfile))
                return public.returnMsg(True,'RENAME_SUCCESS')
            else:
                public.WriteLog('TYPE_FILE', 'MOVE_SUCCESS',
                                (get.sfile, get.dfile))
                return public.returnMsg(True, 'MOVE_SUCCESS')
        except:
            return public.returnMsg(False, 'MOVE_ERR')

    # 检查文件是否存在
    def CheckExistsFiles(self, get):
        if sys.version_info[0] == 2:
            get.dfile = get.dfile.encode('utf-8')
        data = []
        filesx = []
        if not hasattr(get, 'filename'):
            if not 'selected' in session:
                return []
            filesx = json.loads(session['selected']['data'])
        else:
            filesx.append(get.filename)

        for fn in filesx:
            if fn == '.':
                continue
            filename = get.dfile + '/' + fn
            if os.path.exists(filename):
                tmp = {}
                stat = os.stat(filename)
                tmp['filename'] = fn
                tmp['size'] = os.path.getsize(filename)
                tmp['mtime'] = str(int(stat.st_mtime))
                data.append(tmp)
        return data

    # 取文件扩展名
    def __get_ext(self, filename):
        tmp = filename.split('.')
        return tmp[-1]

    # 获取文件内容
    def GetFileBody(self, get):
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')

        get.path = self.xssdecode(get.path)
        if not os.path.exists(get.path):
            if get.path.find('rewrite') == -1:
                return public.returnMsg(False,'FILE_NOT_EXISTS',(get.path,))
            public.writeFile(get.path,'')
        if self.__get_ext(get.path) in ['gz','zip','rar','exe','db','pdf','doc','xls','docx','xlsx','ppt','pptx','7z','bz2','png','gif','jpg','jpeg','bmp','icon','ico','pyc','class','so','pyd']:
            return public.returnMsg(False,'FILE_ONLINE_EDIT_ERR')
        if os.path.getsize(get.path) > 3145928:
            return public.returnMsg(False,'CANT_EDIT_ONLINE_FILE')
        if os.path.isdir(get.path):
            return public.returnMsg(False,'FILE_ERR')

        # 处理my.cnf为空的情况
        myconf_file = '/etc/my.cnf'
        if get.path == myconf_file:
            if os.path.getsize(myconf_file) < 10:
                mycnf_file_bak = '/etc/my.cnf.bak'
                if os.path.exists(mycnf_file_bak):
                    public.writeFile(myconf_file, public.readFile(mycnf_file_bak))

        fp = open(get.path,'rb')
        data = {}
        data['status'] = True

        try:
            if fp:
                srcBody = fp.read()
                fp.close()
                try:
                    data['encoding'] = 'utf-8'
                    data['data'] = srcBody.decode(data['encoding'])
                except:
                    try:
                        data['encoding'] = 'GBK'
                        data['data'] = srcBody.decode(data['encoding'])
                    except:
                        try:
                            data['encoding'] = 'BIG5'
                            data['data'] = srcBody.decode(data['encoding'])
                        except:
                            return public.returnMsg(False, 'FILE_ERR1')
            else:
               return public.returnMsg(False,'FILE_ERR2')
            if hasattr(get,'filename'):
                get.path = get.filename
            data['historys'] = self.get_history(get.path)
            data['auto_save'] = self.get_auto_save(get.path)
            return data
        except Exception as ex:
            return public.returnMsg(False,'INCOMPATIBLE_FILECODE',(str(ex)),)

    #保存文件
    def SaveFileBody(self,get):
        if not 'path' in get:
            return public.returnMsg(False,'PATH_PARA_ERR')
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        if not os.path.exists(get.path):
            if get.path.find('.htaccess') == -1:
                return public.returnMsg(False, 'FILE_NOT_EXISTS')

        his_path = '/www/backup/file_history/'
        if get.path.find(his_path) != -1:
            return public.returnMsg(False,'HISTORY_DIR_ERR')
        try:
            if 'base64' in get:
                import base64
                get.data = base64.b64decode(get.data)
            isConf = -1
            if os.path.exists('/etc/init.d/nginx') or os.path.exists('/etc/init.d/httpd'):
                isConf = get.path.find('nginx')
                if isConf == -1:
                    isConf = get.path.find('apache')
                if isConf == -1:
                    isConf = get.path.find('rewrite')
                if isConf != -1:
                    public.ExecShell('\\cp -a '+get.path+' /tmp/backup.conf')

            data = get.data
            if data == 'undefined': return public.returnMsg(False,'FILE_ERR3')
            userini = False
            if get.path.find('.user.ini') != -1:
                userini = True
                public.ExecShell('chattr -i ' + get.path)

            if get.path.find('/www/server/cron') != -1:
                try:
                    import crontab
                    data = crontab.crontab().CheckScript(data)
                except:
                    pass

            if get.encoding == 'ascii':
                get.encoding = 'utf-8'
            self.save_history(get.path)
            try:
                if sys.version_info[0] == 2:
                    data = data.encode(get.encoding, errors='ignore')
                    fp = open(get.path, 'w+')
                else:

                    data = data.encode(get.encoding , errors='ignore').decode(get.encoding)
                    fp = open(get.path, 'w+', encoding=get.encoding)
            except:
                fp = open(get.path, 'w+')

            fp.write(data)
            fp.close()

            if isConf != -1:
                isError = public.checkWebConfig()
                if isError != True:
                    public.ExecShell('\\cp -a /tmp/backup.conf '+get.path)
                    return public.returnMsg(False, 'ERROR:<br><font style="color:red;">'+isError.replace("\n", '<br>')+'</font>')
                public.serviceReload()

            if userini:
                public.ExecShell('chattr +i ' + get.path)

            public.WriteLog('TYPE_FILE', 'FILE_SAVE_SUCCESS', (get.path,))
            return public.returnMsg(True, 'FILE_SAVE_SUCCESS')
        except Exception as ex:
            return public.returnMsg(False, 'FILE_SAVE_ERR' + str(ex))

    # 保存历史副本
    def save_history(self, filename):
        if os.path.exists('/www/server/panel/data/not_file_history.pl'):
            return True
        try:
            his_path = '/www/backup/file_history/'
            if filename.find(his_path) != -1:
                return
            save_path = (his_path + filename).replace('//', '/')
            if not os.path.exists(save_path):
                os.makedirs(save_path, 384)

            his_list = sorted(os.listdir(save_path), reverse=True)
            num = public.readFile('data/history_num.pl')
            if not num:
                num = 10
            else:
                num = int(num)
            d_num = len(his_list)
            is_write = True
            new_file_md5 = public.FileMd5(filename)
            for i in range(d_num):
                rm_file = save_path + '/' + his_list[i]
                if i == 0:  # 判断是否和上一份副本相同
                    old_file_md5 = public.FileMd5(rm_file)
                    if old_file_md5 == new_file_md5:
                        is_write = False

                if i+1 >= num:  # 删除多余的副本
                    if os.path.exists(rm_file):
                        os.remove(rm_file)
                    continue
            # 写入新的副本
            if is_write:
                public.writeFile(
                    save_path + '/' + str(int(time.time())), public.readFile(filename, 'rb'), 'wb')
        except:
            pass

    # 取历史副本
    def get_history(self, filename):
        try:
            save_path = ('/www/backup/file_history/' +
                         filename).replace('//', '/')
            if not os.path.exists(save_path):
                return []
            return sorted(os.listdir(save_path))
        except:
            return []

    # 读取指定历史副本
    def read_history(self, args):
        save_path = ('/www/backup/file_history/' +
                     args.filename).replace('//', '/')
        args.path = save_path + '/' + args.history
        return self.GetFileBody(args)

    # 恢复指定历史副本
    def re_history(self, args):
        save_path = ('/www/backup/file_history/' +
                     args.filename).replace('//', '/')
        args.path = save_path + '/' + args.history
        if not os.path.exists(args.path):
            return public.returnMsg(False,'HISTORY_ERR')
        import shutil
        shutil.copyfile(args.path, args.filename)
        return self.GetFileBody(args)

    # 自动保存配置
    def auto_save_temp(self, args):
        save_path = '/www/backup/file_auto_save/'
        if not os.path.exists(save_path):
            os.makedirs(save_path, 384)
        filename = save_path + args.filename
        if os.path.exists(filename):
            f_md5 = public.FileMd5(filename)
            s_md5 = public.md5(args.body)
            if f_md5 == s_md5:
                return public.returnMsg(True,'NOT_EDIT')
        public.writeFile(filename,args.body)
        return public.returnMsg(True,'AUTO_SAVE')

    # 取上一次自动保存的结果
    def get_auto_save_body(self, args):
        save_path = '/www/backup/file_auto_save/'
        args.path = save_path + args.filename
        return self.GetFileBody(args)

    # 取自动保存结果
    def get_auto_save(self, filename):
        try:
            save_path = ('/www/backup/file_auto_save/' +
                         filename).replace('//', '/')
            if not os.path.exists(save_path):
                return None
            return os.stat(save_path).st_mtime
        except:
            return None

    # 文件压缩
    def Zip(self, get):
        if not 'z_type' in get:
            get.z_type = 'rar'

        if get.z_type == 'rar':
            if os.uname().machine == 'aarch64':
                return public.returnMsg(False,'RAR component does not support aarch 64 platform')

        import panelTask
        task_obj = panelTask.bt_task()
        task_obj.create_task(public.GetMsg("COMPRESSION_FILE"),3,get.path,json.dumps({"sfile":get.sfile,"dfile":get.dfile,"z_type":get.z_type}))
        public.WriteLog("TYPE_FILE", 'ZIP_SUCCESS',(get.sfile,get.dfile))
        return public.returnMsg(True,'ADD_COMPRESSION_TO_LINEUP')

    # 文件解压
    def UnZip(self, get):
        import panelTask
        if not 'password' in get:
            get.password = ''
        task_obj = panelTask.bt_task()
        task_obj.create_task(public.GetMsg("DECOMPRESSION_FILE"),2,get.sfile,json.dumps({"dfile":get.dfile,"password":get.password}))
        public.WriteLog("TYPE_FILE", 'UNZIP_SUCCESS',(get.sfile,get.dfile))
        return public.returnMsg(True,'ADD_DECOMPRESSION_TO_LINEUP')
    
    
    #获取文件/目录 权限信息
    def GetFileAccess(self,get):
        if sys.version_info[0] == 2:
            get.filename = get.filename.encode('utf-8')
        data = {}
        try:
            import pwd
            stat = os.stat(get.filename)
            data['chmod'] = str(oct(stat.st_mode)[-3:])
            data['chown'] = pwd.getpwuid(stat.st_uid).pw_name
        except:
            data['chmod'] = 644
            data['chown'] = 'www'
        return data

    # 设置文件权限和所有者
    def SetFileAccess(self, get, all='-R'):
        if sys.version_info[0] == 2:
            get.filename = get.filename.encode('utf-8')
        if 'all' in get:
            if get.all == 'False':
                all = ''
        try:
            if not self.CheckDir(get.filename):
                return public.returnMsg(False, 'FILE_DANGER')
            if not os.path.exists(get.filename):
                return public.returnMsg(False, 'FILE_NOT_EXISTS')
            public.ExecShell('chmod '+all+' '+get.access+" '"+get.filename+"'")
            public.ExecShell('chown '+all+' '+get.user+':' +
                             get.user+" '"+get.filename+"'")
            public.WriteLog('TYPE_FILE', 'FILE_ACCESS_SUCCESS',
                            (get.filename, get.access, get.user))
            return public.returnMsg(True, 'SET_SUCCESS')
        except:
            return public.returnMsg(False, 'SET_ERROR')

    def SetFileAccept(self, filename):
        public.ExecShell('chown -R www:www ' + filename)
        if os.path.isfile(filename):
            public.ExecShell('chmod -R 644 ' + filename)
        else:
            public.ExecShell('chmod -R 755 ' + filename)

    # 取目录大小

    def GetDirSize(self, get):
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        return public.to_size(public.get_path_size(get.path))

    # 取目录大小2
    def get_path_size(self, get):
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        data = {}
        data['path'] = get.path
        data['size'] = public.get_path_size(get.path)
        return data

    def CloseLogs(self, get):
        get.path = public.GetConfigValue('root_path')
        public.ExecShell('rm -f '+public.GetConfigValue('logs_path')+'/*')
        public.ExecShell('rm -rf '+public.GetConfigValue('logs_path')+'/history_backups/*')
        public.ExecShell('rm -f '+public.GetConfigValue('logs_path')+'/pm2/*.log')
        if public.get_webserver() == 'nginx':
            public.ExecShell(
                'kill -USR1 `cat '+public.GetConfigValue('setup_path')+'/nginx/logs/nginx.pid`')
        else:
            public.ExecShell('/etc/init.d/httpd reload')

        public.WriteLog('TYPE_FILE', 'SITE_LOG_CLOSE')
        get.path = public.GetConfigValue('logs_path')
        return self.GetDirSize(get)

    # 批量操作
    def SetBatchData(self, get):
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        if get.type == '1' or get.type == '2':
            session['selected'] = get
            return public.returnMsg(True, 'FILE_ALL_TIPS')
        elif get.type == '3':
            for key in json.loads(get.data):
                try:
                    if sys.version_info[0] == 2:
                        key = key.encode('utf-8')
                    filename = get.path+'/'+key
                    if not self.CheckDir(filename):
                        return public.returnMsg(False, 'FILE_DANGER')
                    ret = ' -R '
                    if 'all' in get:
                        if get.all == 'False':
                            ret = ''
                    public.ExecShell('chmod '+ret+get.access+" '"+filename+"'")
                    public.ExecShell('chown '+ret+get.user +
                                     ':'+get.user+" '"+filename+"'")
                except:
                    continue
            public.WriteLog('TYPE_FILE', 'FILE_ALL_ACCESS')
            return public.returnMsg(True, 'FILE_ALL_ACCESS')
        else:
            isRecyle = os.path.exists('data/recycle_bin.pl') and session.get('debug') != 1
            path = get.path
            get.data = json.loads(get.data)
            l = len(get.data)
            i = 0
            for key in get.data:
                try:
                    if sys.version_info[0] == 2:
                        key = key.encode('utf-8')
                    filename = path + '/'+key
                    get.path = filename
                    if not os.path.exists(filename):
                        continue
                    i += 1
                    public.writeSpeed(key, i, l)
                    if os.path.isdir(filename):
                        if not self.CheckDir(filename):
                            return public.returnMsg(False, 'FILE_DANGER')
                        public.ExecShell("chattr -R -i " + filename)
                        if isRecyle:
                            self.Mv_Recycle_bin(get)
                        else:
                            shutil.rmtree(filename)
                    else:
                        if key == '.user.ini':
                            if l > 1:
                                continue
                            public.ExecShell('chattr -i ' + filename)
                        if isRecyle:

                            self.Mv_Recycle_bin(get)
                        else:
                            os.remove(filename)
                except:
                    continue
                public.writeSpeed(None, 0, 0)
            self.site_path_safe(get)
            public.WriteLog('TYPE_FILE', 'FILE_ALL_DEL')
            return public.returnMsg(True, 'FILE_ALL_DEL')

    # 批量粘贴
    def BatchPaste(self, get):
        import shutil
        if sys.version_info[0] == 2:
            get.path = get.path.encode('utf-8')
        if not self.CheckDir(get.path):
            return public.returnMsg(False,'FILE_DANGER')
        if not 'selected' in session:
            return public.returnMsg(False,'TCOPY_PRESS_ERR')
        i = 0
        if not 'selected' in session:
            return public.returnMsg(False,'OPERA_FAILED')
        myfiles = json.loads(session['selected']['data'])
        l = len(myfiles)
        if get.type == '1':

            for key in myfiles:
                if sys.version_info[0] == 2:
                    sfile = session['selected']['path'] + \
                        '/' + key.encode('utf-8')
                    dfile = get.path + '/' + key.encode('utf-8')
                else:
                    sfile = session['selected']['path'] + '/' + key
                    dfile = get.path + '/' + key

                if dfile.find(sfile) == 0:
                    return public.returnMsg(False,'Wrong copy logic, from {} copy to {} has an inclusive relationship, there is an infinite loop copy risk!'.format(sfile,dfile))

            for key in myfiles:
                i += 1
                public.writeSpeed(key, i, l)
                try:
                    if sys.version_info[0] == 2:
                        sfile = session['selected']['path'] + '/' + key.encode('utf-8')
                        dfile = get.path + '/' + key.encode('utf-8')
                    else:
                        sfile = session['selected']['path'] + '/' + key
                        dfile = get.path + '/' + key

                    if os.path.isdir(sfile):
                        self.copytree(sfile, dfile)
                    else:
                        shutil.copyfile(sfile, dfile)
                    stat = os.stat(sfile)
                    os.chown(dfile, stat.st_uid, stat.st_gid)
                except:
                    continue
            public.WriteLog('TYPE_FILE','FILE_ALL_COPY',(session['selected']['path'],get.path))
        else:
            for key in myfiles:
                try:
                    i += 1
                    public.writeSpeed(key, i, l)
                    if sys.version_info[0] == 2:
                        sfile = session['selected']['path'] + '/' + key.encode('utf-8')
                        dfile = get.path + '/' + key.encode('utf-8')
                    else:
                        sfile = session['selected']['path'] + '/' + key
                        dfile = get.path + '/' + key
                    self.move(sfile, dfile)
                except:
                    continue
            self.site_path_safe(get)
            public.WriteLog('TYPE_FILE','FILE_ALL_MOTE',(session['selected']['path'],get.path))
        public.writeSpeed(None,0,0);
        errorCount = len(myfiles) - i
        del(session['selected'])
        return public.returnMsg(True,'FILE_ALL',(str(i),str(errorCount)))

    # 移动和重命名
    def move(self, sfile, dfile):
        sfile = sfile.replace('//', '/')
        dfile = dfile.replace('//', '/')
        if sfile == dfile:
            return False
        if not os.path.exists(sfile):
            return False
        is_dir = os.path.isdir(sfile)
        if not os.path.exists(dfile) or not is_dir:
            if os.path.exists(dfile):
                os.remove(dfile)
            shutil.move(sfile, dfile)
        else:
            self.copytree(sfile, dfile)
            if os.path.exists(sfile) and os.path.exists(dfile):
                if is_dir:
                    shutil.rmtree(sfile)
                else:
                    os.remove(sfile)
        return True

    # 复制目录
    def copytree(self, sfile, dfile):
        if sfile == dfile:
            return False
        if not os.path.exists(dfile):
            os.makedirs(dfile)
        for f_name in os.listdir(sfile):
            if not f_name.strip(): continue
            if f_name.find('./') != -1: continue
            src_filename = (sfile + '/' + f_name).replace('//', '/')
            dst_filename = (dfile + '/' + f_name).replace('//', '/')
            mode_info = public.get_mode_and_user(src_filename)
            if os.path.isdir(src_filename):
                if not os.path.exists(dst_filename):
                    os.makedirs(dst_filename)
                    public.set_mode(dst_filename, mode_info['mode'])
                    public.set_own(dst_filename, mode_info['user'])
                self.copytree(src_filename, dst_filename)
            else:
                try:
                    shutil.copy2(src_filename, dst_filename)
                    public.set_mode(dst_filename, mode_info['mode'])
                    public.set_own(dst_filename, mode_info['user'])
                except:
                    pass
        return True

    # 下载文件

    def DownloadFile(self, get):
        import panelTask
        task_obj = panelTask.bt_task()
        task_obj.create_task(public.GetMsg("DOWNLOAD_FILE"),1,get.url,get.path + '/' + get.filename)
        #if sys.version_info[0] == 2: get.path = get.path.encode('utf-8');
        #import db,time
        #isTask = '/tmp/panelTask.pl'
        #execstr = get.url +'|bt|'+get.path+'/'+get.filename
        #sql = db.Sql()
        #sql.table('tasks').add('name,type,status,addtime,execstr',('下载文件['+get.filename+']','download','0',time.strftime('%Y-%m-%d %H:%M:%S'),execstr))
        # public.writeFile(isTask,'True')
        # self.SetFileAccept(get.path+'/'+get.filename)
        public.WriteLog('TYPE_FILE', 'FILE_DOWNLOAD', (get.url, get.path))
        return public.returnMsg(True, 'FILE_DOANLOAD')

    # 添加安装任务
    def InstallSoft(self, get):
        import db
        import time
        path = public.GetConfigValue('setup_path') + '/php'
        if not os.path.exists(path):
            public.ExecShell("mkdir -p " + path)
        if session['server_os']['x'] != 'RHEL':
            get.type = '3'
        apacheVersion = 'false'
        if public.get_webserver() == 'apache':
            apacheVersion = public.readFile(
                public.GetConfigValue('setup_path')+'/apache/version.pl')
        public.writeFile('/var/bt_apacheVersion.pl', apacheVersion)
        public.writeFile('/var/bt_setupPath.conf',
                         public.GetConfigValue('root_path'))
        isTask = '/tmp/panelTask.pl'
        execstr = "cd " + public.GetConfigValue('setup_path') + "/panel/install && /bin/bash install_soft.sh " + \
            get.type + " install " + get.name + " " + get.version
        if public.get_webserver() == "openlitespeed":
            execstr = "cd " + public.GetConfigValue('setup_path') + "/panel/install && /bin/bash install_soft.sh " + \
                      get.type + " install " + get.name + "-ols " + get.version
        sql = db.Sql()
        if hasattr(get, 'id'):
            id = get.id
        else:
            id = None
        sql.table('tasks').add('id,name,type,status,addtime,execstr', (None,
                                                                       'Install ['+get.name+'-'+get.version+']', 'execshell', '0', time.strftime('%Y-%m-%d %H:%M:%S'), execstr))
        public.writeFile(isTask, 'True')
        public.WriteLog('TYPE_SETUP', 'PLUGIN_ADD', (get.name, get.version))
        time.sleep(0.1)
        return public.returnMsg(True, 'PLUGIN_ADD')

    # 删除任务队列
    def RemoveTask(self, get):
        try:
            name = public.M('tasks').where('id=?', (get.id,)).getField('name')
            status = public.M('tasks').where(
                'id=?', (get.id,)).getField('status')
            public.M('tasks').delete(get.id)
            if status == '-1':
                public.ExecShell(
                    "kill `ps -ef |grep 'python panelSafe.pyc'|grep -v grep|grep -v panelExec|awk '{print $2}'`")
                public.ExecShell(
                    "kill `ps -ef |grep 'install_soft.sh'|grep -v grep|grep -v panelExec|awk '{print $2}'`")
                public.ExecShell(
                    "kill `ps aux | grep 'python task.pyc$'|awk '{print $2}'`")
                public.ExecShell('''
pids=`ps aux | grep 'sh'|grep -v grep|grep install|awk '{print $2}'`
arr=($pids)

for p in ${arr[@]}
do
    kill -9 $p
done
            ''')

                public.ExecShell(
                    'rm -f ' + name.replace('Scan dir [', '').replace(']', '') + '/scan.pl')
                isTask = '/tmp/panelTask.pl'
                public.writeFile(isTask, 'True')
                public.ExecShell('/etc/init.d/bt start')
        except:
            public.ExecShell('/etc/init.d/bt start')
        return public.returnMsg(True, 'PLUGIN_DEL')

    # 重新激活任务
    def ActionTask(self, get):
        isTask = '/tmp/panelTask.pl'
        public.writeFile(isTask, 'True')
        return public.returnMsg(True, 'PLUGIN_ACTION')

    # 卸载软件
    def UninstallSoft(self, get):
        public.writeFile('/var/bt_setupPath.conf',
                         public.GetConfigValue('root_path'))
        get.type = '0'
        if session['server_os']['x'] != 'RHEL':
            get.type = '3'
        if public.get_webserver() == "openlitespeed":
            default_ext = ["bz2","calendar","sysvmsg","exif","imap","readline","sysvshm","xsl"]
            if get.version == "73":
                default_ext.append("opcache")
            if not os.path.exists("/etc/redhat-release"):
                default_ext.append("gmp")
                default_ext.append("opcache")
            if get.name.lower() in default_ext:
                return public.returnMsg(False, "PHP_EXTENSION_UNINSTALL_ERR")
        execstr = "cd " + public.GetConfigValue('setup_path') + "/panel/install && /bin/bash install_soft.sh " + \
            get.type+" uninstall " + get.name.lower() + " " + get.version.replace('.', '')
        if public.get_webserver() == "openlitespeed":
            execstr = "cd " + public.GetConfigValue('setup_path') + "/panel/install && /bin/bash install_soft.sh " + \
                      get.type + " uninstall " + get.name.lower() + "-ols " + get.version.replace('.', '')
        public.ExecShell(execstr)
        public.WriteLog('TYPE_SETUP', 'PLUGIN_UNINSTALL',
                        (get.name, get.version))
        return public.returnMsg(True, "PLUGIN_UNINSTALL")

    # 取任务队列进度
    def GetTaskSpeed(self, get):
        tempFile = '/tmp/panelExec.log'
        #freshFile = '/tmp/panelFresh'
        import db
        find = db.Sql().table('tasks').where('status=? OR status=?',('-1','0')).field('id,type,name,execstr').find()
        if(type(find) == str):
            return public.returnMsg(False,"QUERY_ERR",(find,))
        if not len(find):
            return public.returnMsg(False,'NO_TASK_AT_LINEUP',("-2",))
        isTask = '/tmp/panelTask.pl'
        public.writeFile(isTask, 'True')
        echoMsg = {}
        echoMsg['name'] = find['name']
        echoMsg['execstr'] = find['execstr']
        if find['type'] == 'download':
            try:
                tmp = public.readFile(tempFile)
                if len(tmp) < 10:
                    return public.returnMsg(False,'NO_TASK_AT_LINEUP',("-3",))
                echoMsg['msg'] = json.loads(tmp)
                echoMsg['isDownload'] = True
            except:
                db.Sql().table('tasks').where("id=?",(find['id'],)).save('status',('0',))
                return public.returnMsg(False,'NO_TASK_AT_LINEUP',("-4",))
        else:
            echoMsg['msg'] = self.GetLastLine(tempFile, 20)
            echoMsg['isDownload'] = False

        echoMsg['task'] = public.M('tasks').where("status!=?", ('1',)).field(
            'id,status,name,type').order("id asc").select()
        return echoMsg

    # 取执行日志
    def GetExecLog(self, get):
        return self.GetLastLine('/tmp/panelExec.log', 100)

    # 读文件指定倒数行数
    def GetLastLine(self, inputfile, lineNum):
        result = public.GetNumLines(inputfile, lineNum)
        if len(result) < 1:
            return public.getMsg('TASK_SLEEP')
        return result

    # 执行SHELL命令
    def ExecShell(self, get):
        disabled = ['vi', 'vim', 'top', 'passwd', 'su']
        get.shell = get.shell.strip()
        tmp = get.shell.split(' ')
        if tmp[0] in disabled:
            return public.returnMsg(False, 'FILE_SHELL_ERR', (tmp[0],))
        shellStr = '''#!/bin/bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
cd %s
%s
''' % (get.path, get.shell)
        public.writeFile('/tmp/panelShell.sh', shellStr)
        public.ExecShell(
            'nohup bash /tmp/panelShell.sh > /tmp/panelShell.pl 2>&1 &')
        return public.returnMsg(True, 'FILE_SHELL_EXEC')

    # 取SHELL执行结果
    def GetExecShellMsg(self, get):
        fileName = '/tmp/panelShell.pl'
        if not os.path.exists(fileName):
            return 'FILE_SHELL_EMPTY'
        status = not public.process_exists('bash', None, '/tmp/panelShell.sh')
        return public.returnMsg(status, public.GetNumLines(fileName, 200))

    # 文件搜索
    def GetSearch(self, get):
        if not os.path.exists(get.path):
            return public.returnMsg(False, 'DIR_NOT_EXISTS')
        return public.ExecShell("find "+get.path+" -name '*"+get.search+"*'")

    # 保存草稿
    def SaveTmpFile(self, get):
        save_path = '/www/server/panel/temp'
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        get.path = os.path.join(save_path,public.Md5(get.path) + '.tmp')
        public.writeFile(get.path,get.body)
        return public.returnMsg(True,'HAVE_BEEN_SAVE')

    # 获取草稿
    def GetTmpFile(self, get):
        self.CleanOldTmpFile()
        save_path = '/www/server/panel/temp'
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        src_path = get.path
        get.path = os.path.join(save_path,public.Md5(get.path) + '.tmp')
        if not os.path.exists(get.path):
            return public.returnMsg(False,'HAVE_NOT_DRAFT')
        data = self.GetFileInfo(get.path)
        data['file'] = src_path
        if 'rebody' in get:
            data['body'] = public.readFile(get.path)
        return data

    # 清除过期草稿
    def CleanOldTmpFile(self):
        if 'clean_tmp_file' in session:
            return True
        save_path = '/www/server/panel/temp'
        max_time = 86400 * 30
        now_time = time.time()
        for tmpFile in os.listdir(save_path):
            filename = os.path.join(save_path, tmpFile)
            fileInfo = self.GetFileInfo(filename)
            if now_time - fileInfo['modify_time'] > max_time:
                os.remove(filename)
        session['clean_tmp_file'] = True
        return True

    # 取指定文件信息
    def GetFileInfo(self, path):
        if not os.path.exists(path):
            return False
        stat = os.stat(path)
        fileInfo = {}
        fileInfo['modify_time'] = int(stat.st_mtime)
        fileInfo['size'] = os.path.getsize(path)
        return fileInfo

    # 安装rar组件
    def install_rar(self, get):
        unrar_file = '/www/server/rar/unrar'
        rar_file = '/www/server/rar/rar'
        bin_unrar = '/usr/local/bin/unrar'
        bin_rar = '/usr/local/bin/rar'
        if os.path.exists(unrar_file) and os.path.exists(bin_unrar):
            try:
                import rarfile
            except:
                public.ExecShell("pip install rarfile")
            return True

        import platform
        os_bit = ''
        if platform.machine() == 'x86_64':
            os_bit = '-x64'
        download_url = public.get_url() + '/src/rarlinux'+os_bit+'-5.6.1.tar.gz'

        tmp_file = '/tmp/bt_rar.tar.gz'
        public.ExecShell('wget -O ' + tmp_file + ' ' + download_url)
        if os.path.exists(unrar_file):
            public.ExecShell("rm -rf /www/server/rar")
        public.ExecShell("tar xvf " + tmp_file + ' -C /www/server/')
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        if not os.path.exists(unrar_file):
            return False

        if os.path.exists(bin_unrar):
            os.remove(bin_unrar)
        if os.path.exists(bin_rar):
            os.remove(bin_rar)

        public.ExecShell('ln -sf ' + unrar_file + ' ' + bin_unrar)
        public.ExecShell('ln -sf ' + rar_file + ' ' + bin_rar)
        public.ExecShell("pip install rarfile")
        # public.writeFile('data/restart.pl','True')
        return True

    def get_store_data(self):
        data = []
        path = 'data/file_store.json'
        try:
            if os.path.exists(path):
                data = json.loads(public.readFile(path))
        except:
            data = []
        if type(data) == dict:
            result = []
            for key in data:
                for path in data[key]:
                    result.append(path)
            self.set_store_data(result)
            return result
        return data

    def set_store_data(self, data):
        public.writeFile('data/file_store.json', json.dumps(data))
        return True

    # 获取收藏夹
    def get_files_store(self, get):
        data = self.get_store_data()
        result = []
        for path in data:
            if type(path) == dict:
                path = path['path']
            info = {'path': path, 'name': os.path.basename(path)}
            if os.path.isdir(path):
                info['type'] = 'dir'
            else:
                info['type'] = 'file'
            result.append(info)
        return result

    # 添加收藏夹
    def add_files_store(self, get):
        path = get.path
        if not os.path.exists(path):
            return public.returnMsg(False,'FILE_DIR_NOT_EXIST')
        data = self.get_store_data()
        if path in data:
            return public.returnMsg(False,'ADD_REPEATEDLY')
        data.append(path)
        self.set_store_data(data)
        return public.returnMsg(True,'ADD_SUCCESS')

    #删除收藏夹
    def del_files_store(self,get):
        path = get.path
        data = self.get_store_data()
        if not path in data:
            is_go = False
            for info in data:
                if type(info) == dict:
                    if info['path'] == path:
                        path = info
                        is_go = True
                        break
            if not is_go:
                return public.returnMsg(False,'FAVORITE_NOT_FOUND')
        data.remove(path)
        if len(data) <= 0:
            data = []
        self.set_store_data(data)
        return public.returnMsg(True,'DEL_SUCCESS')

    # #单文件木马扫描
    # def file_webshell_check(self,get):
    #     if not 'filename' in get: return public.returnMsg(True, 'file does not exist!')
    #     import webshell_check
    #     if webshell_check.webshell_check().upload_file_url(get.filename.strip()):
    #         return public.returnMsg(False,'This file is webshell [ %s ]'%get.filename.strip().split('/')[-1])
    #     else:
    #         return public.returnMsg(True, 'no risk')
    #
    # #目录扫描木马
    # def dir_webshell_check(self,get):
    #     if not 'path' in get: return public.returnMsg(False, 'Please enter a valid directory!')
    #     path=get.path.strip()
    #     if os.path.exists(path):
    #         #启动消息队列
    #         exec_shell = public.get_python_bin() + ' /www/server/panel/class/webshell_check.py dir %s mail'%path
    #         task_name = "Scan Trojan files for directory %s"%path
    #         import panelTask
    #         task_obj = panelTask.bt_task()
    #         task_obj.create_task(task_name, 0, exec_shell)
    #         return public.returnMsg(True, 'Starting Trojan killing process. Details will be in the panel security log')

    # 获取下载地址列表
    def get_download_url_list(self, get):
        my_table = 'download_token'
        count = public.M(my_table).count()

        if not 'p' in get:
            get.p = 1
        if not 'collback' in get:
            get.collback = ''
        data = public.get_page(count, int(get.p), 12, get.collback)
        data['data'] = public.M(my_table).order('id desc').field(
            'id,filename,token,expire,ps,total,password,addtime').limit(data['shift'] + ',' + data['row']).select()
        return data

    # 获取短列表
    def get_download_list(self):
        if self.download_list: return self.download_list
        my_table = 'download_token'
        data = public.M(my_table).field('id,filename,expire').select()
        self.download_list = data
        return data

    # 获取id
    def get_download_id(self, filename):
        download_list = self.get_download_list()
        my_table = 'download_token'
        m_time = time.time()
        result = '0'
        for d in download_list:
            if filename == d['filename']:
                result = str(d['id'])
                break

            # 清理过期和无效
            if self.download_is_rm: continue
            if not os.path.exists(d['filename']) or m_time > d['expire']:
                public.M(my_table).where('id=?', (d['id'],)).delete()
        # 标记清理
        if not self.download_is_rm:
            self.download_is_rm = True
        return result

    # 获取指定下载地址
    def get_download_url_find(self, get):
        if not 'id' in get: return public.returnMsg(False, 'WRONG_PARAMETER')
        id = int(get.id)
        my_table = 'download_token'
        data = public.M(my_table).where('id=?', (id,)).find()
        if not data: return public.returnMsg(False, 'ADDRESS_NOT_EXIST')
        return data

    # 删除下载地址
    def remove_download_url(self, get):
        if not 'id' in get: return public.returnMsg(False, 'WRONG_PARAMETER')
        id = int(get.id)
        my_table = 'download_token'
        public.M(my_table).where('id=?', (id,)).delete()
        return public.returnMsg(True, 'DEL_SUCCESS')

    # 修改下载地址
    def modify_download_url(self, get):
        if not 'id' in get: return public.returnMsg(False, 'WRONG_PARAMETER')
        id = int(get.id)
        my_table = 'download_token'
        if not public.M(my_table).where('id=?', (id,)).count():
            return public.returnMsg(False, 'ADDRESS_NOT_EXIST')
        pdata = {}
        if 'expire' in get: pdata['expire'] = get.expire
        if 'password' in get:
            pdata['password'] = get.password
            if len(pdata['password']) < 4 and len(pdata['password']) > 0:
                return public.returnMsg(False,'The length of the extracted password cannot be less than 4 digits')
            if not re.match('^\w+$',pdata['password']):
                return public.returnMsg(False,'The password only supports a combination of uppercase and lowercase letters and numbers')

        if 'ps' in get: pdata['ps'] = get.ps
        public.M(my_table).where('id=?', (id,)).update(pdata)
        return public.returnMsg(True, 'EDIT_SUCCESS')

    # 生成下载地址
    def create_download_url(self, get):
        if not os.path.exists(get.filename):
            return public.returnMsg(False,'FILE_DIR_NOT_EXIST')
        my_table = 'download_token'
        mtime = int(time.time())
        pdata = {
            "filename": get.filename,               #文件名
            "token": public.GetRandomString(12),    #12位随机密钥，用于URL
            "expire": mtime + (int(get.expire) * 3600), #过期时间
            "ps":get.ps, #备注
            "total":0,  #下载计数
            "password":str(get.password), #提取密码
            "addtime": mtime #添加时间
        }
        if len(pdata['password']) < 4 and len(pdata['password']) > 0:
            return public.returnMsg(False,'PASSWD_ERR')
        if not re.match('^\w+$',pdata['password']) and pdata['password']:
            return public.returnMsg(False,'The password only supports a combination of uppercase and lowercase letters and numbers')
        #更新 or 插入
        token = public.M(my_table).where('filename=?',(get.filename,)).getField('token')
        if token:
            return public.returnMsg(False, 'ALREADY_SHARED')
            # pdata['token'] = token
            # del(pdata['total'])
            # public.M(my_table).where('token=?',(token,)).update(pdata)
        else:
            id = public.M(my_table).insert(pdata)
            pdata['id'] = id

        return public.returnMsg(True, pdata)


    #取PHP-CLI执行命令
    def __get_php_bin(self,php_version=None):
        php_vs = ["80","74","73","72","71","70","56","55","54","53"]
        if php_version:
            if php_version != 'auto':
                if not php_version in php_vs: return ''
            else:
                php_version = None

        #判段兼容的PHP版本是否安装
        php_path = "/www/server/php/"
        php_v = None
        for pv in php_vs:
            if php_version:
                if php_version != pv: continue
            php_bin = php_path + pv + "/bin/php"
            if os.path.exists(php_bin):
                php_v = pv
                break
        # 如果没安装直接返回False
        if not php_v: return ''
        #处理PHP-CLI-INI配置文件
        php_ini = '/www/server/panel/tmp/composer_php_cli_'+php_v+'.ini'
        if not os.path.exists(php_ini):
            # 如果不存在，则从PHP安装目录下复制一份
            src_php_ini = php_path + php_v + '/etc/php.ini'
            import shutil
            shutil.copy(src_php_ini, php_ini)
            # 解除所有禁用函数
            php_ini_body = public.readFile(php_ini)
            php_ini_body = re.sub(r"disable_functions\s*=.*", "disable_functions = ", php_ini_body)
            public.writeFile(php_ini, php_ini_body)
        return php_path + php_v + '/bin/php -c ' + php_ini

    # 执行git
    def exec_git(self,get):
        if get.git_action == 'option':
            public.ExecShell("nohup {} &> /tmp/panelExec.pl &".format(get.giturl))
        else:
            public.ExecShell("nohup git clone {} &> /tmp/panelExec.pl &".format(get.giturl))
        return public.returnMsg(True,'COMMAND_SENT')

    # 安装composer
    def get_composer_bin(self):
        composer_bin = '/usr/bin/composer'
        download_addr = 'wget -O {} {}/install/src/composer.phper -T 5'.format(composer_bin,public.get_url())
        if not os.path.exists(composer_bin):
            public.ExecShell(download_addr)
        elif os.path.getsize(composer_bin) < 100:
            public.ExecShell(download_addr)

        public.ExecShell('chmod +x {}'.format(composer_bin))
        if not os.path.exists(composer_bin):
            return False
        return composer_bin

    # 执行composer
    def exec_composer(self,get):
        #准备执行环境
        composer_bin = self.get_composer_bin()
        if not composer_bin:
            return public.returnMsg(False,'NO_COMPOSER_AVAILABLE')

        #取执行PHP版本
        php_version = None
        if 'php_version' in get:
            php_version = get.php_version
        php_bin = self.__get_php_bin(php_version)
        if not php_bin:
            return public.returnMsg(False,'PHP_VER_NOT_FOUND')
        get.composer_cmd = get.composer_cmd.strip()
        if get.composer_cmd == '':
            if not os.path.exists(get.path + '/composer.json'):
                return public.returnMsg(False,'COMPOSER_CONF_NOT_FOUND')
        log_file = '/tmp/composer.log'
        user = ''
        if 'user' in get:
            user = 'sudo -u {} '.format(get.user)
            if not os.path.exists('/usr/bin/sudo'):
                if os.path.exists('/usr/bin/apt'):
                    public.ExecShell("apt install sudo -y > {}".format(log_file))
                else:
                    public.ExecShell("yum install sudo -y > {}".format(log_file))
            public.ExecShell("mkdir -p /home/www && chown -R www:www /home/www")

        #设置指定源
        if 'repo' in get:
            if get.repo != 'repos.packagist':
                public.ExecShell('export COMPOSER_HOME=/tmp && {}{} {} config -g repo.packagist composer {}'.format(user,php_bin,composer_bin,get.repo))
            else:
                public.ExecShell('export COMPOSER_HOME=/tmp && {}{} {} config -g --unset repos.packagist'.format(user,php_bin,composer_bin))
        #执行composer命令
        if not get.composer_cmd:
            composer_exec_str = '{} {} {} -vvv'.format(php_bin,composer_bin,get.composer_args)
        else:
            if get.composer_cmd.find('composer ') == 0 or get.composer_cmd.find('/usr/bin/composer ') == 0:
                composer_cmd = get.composer_cmd.replace('composer ','').replace('/usr/bin/composer ','')
                composer_exec_str = '{} {} {} -vvv'.format(php_bin,composer_bin,composer_cmd)
            else:
                composer_exec_str = '{} {} {} {} -vvv'.format(php_bin,composer_bin,get.composer_args,get.composer_cmd)

        if os.path.exists(log_file): os.remove(log_file)
        public.ExecShell("cd {} && export COMPOSER_HOME=/tmp && {} nohup {} &> {} && echo 'BT-Exec-Completed' >> {}  && rm -rf /home/www &".format(get.path,user,composer_exec_str,log_file,log_file))
        public.WriteLog('Composer',"EXEC_COMPOSER",(get.path,get.composer_args))
        return public.returnMsg(True,'COMMAND_SENT')

    # 取composer版本
    def get_composer_version(self,get):
        composer_bin = self.get_composer_bin()
        if not composer_bin:
            return public.returnMsg(False,'NO_COMPOSER_AVAILABLE')

        try:
            bs = str(public.readFile(composer_bin,'rb'))
            result = re.findall(r"const VERSION\s*=\s*.{0,2}'([\d\.]+)",bs)[0]
            if not result: raise Exception('empty!')
        except:
            php_bin = self.__get_php_bin()
            if not php_bin:  return public.returnMsg(False,'No available PHP version found!')
            composer_exec_str = 'export COMPOSER_HOME=/tmp && ' + php_bin + ' ' + composer_bin +' --version 2>/dev/null|grep \'Composer version\'|awk \'{print $3}\''
            result = public.ExecShell(composer_exec_str)[0].strip()
        data = public.returnMsg(True,result)
        if 'path' in get:
            import panelSite
            data['php_versions'] = panelSite.panelSite().GetPHPVersion(get)
            data['comp_json'] = True
            data['comp_lock'] = False
            if not os.path.exists(get.path + '/composer.json'):
                data['comp_json'] = public.getMsg('COMPOSER_CONF_NOT_EXIST')
            if os.path.exists(get.path + '/composer.lock'):
                data['comp_lock'] = public.getMsg('COMPOSERLOGCK_EXIST')
        return data

    # 升级composer版本
    def update_composer(self,get):
        composer_bin = self.get_composer_bin()
        if not composer_bin:
            return public.returnMsg(False,'NO_COMPOSER_AVAILABLE')
        php_bin = self.__get_php_bin()
        if not php_bin:  return public.returnMsg(False,'No available PHP version found!')
        #设置指定源
        # if 'repo' in get:
        #     if get.repo:
        #         public.ExecShell('{} {} config -g repo.packagist composer {}'.format(php_bin,composer_bin,get.repo))

        version1 = self.get_composer_version(get)['msg']
        composer_exec_str = 'export COMPOSER_HOME=/tmp && {} {} self-update -vvv'.format(php_bin,composer_bin)
        public.ExecShell(composer_exec_str)
        version2 = self.get_composer_version(get)['msg']
        if version1 == version2:
            msg = public.getMsg("COMPOSER_UPDATE_ERR")
        else:
            msg = public.getMsg("COMPOSER_UPDATE",(version1,version2))
            public.WriteLog('Composer',msg)
        return public.returnMsg(True,msg)

    # 计算文件HASH
    def get_file_hash(self,args=None,filename=None):
        if not filename: filename = args.filename
        import hashlib
        md5_obj = hashlib.md5()
        sha1_obj = hashlib.sha1()
        f = open(filename,'rb')
        while True:
            b = f.read(8096)
            if not b :
                break
            md5_obj.update(b)
            sha1_obj.update(b)
        f.close()
        return {'md5':md5_obj.hexdigest(),'sha1':sha1_obj.hexdigest()}


    # 取历史副本
    def get_history_info(self, filename):
        try:
            save_path = ('/www/backup/file_history/' +
                         filename).replace('//', '/')
            if not os.path.exists(save_path):
                return []
            result = []
            for f in  sorted(os.listdir(save_path)):
                f_name = (save_path + '/' + f).replace('//', '/')
                pdata = {}
                pdata['md5'] = public.FileMd5(f_name)
                f_stat = os.stat(f_name)
                pdata['st_mtime'] = int(f)
                pdata['st_size'] = f_stat.st_size
                pdata['history_file'] = f_name
                result.append(pdata)
            return result
        except:
            return []

    #获取文件扩展名
    def get_file_ext(self,filename):
        ss_exts = ['tar.gz','tar.bz2','tar.bz']
        for s in ss_exts:
            e_len = len(s)
            f_len = len(filename)
            if f_len < e_len: continue
            if filename[-e_len:] == s:
                return s
        if filename.find('.') == -1: return ''
        return filename.split('.')[-1]


    # 取所属用户或组
    def get_mode_user(self,uid):
        import pwd
        try:
            return pwd.getpwuid(uid).pw_name
        except:
            return uid

    # 取lsattr
    def get_lsattr(self,filename):
        if os.path.isfile(filename):
            return public.ExecShell('lsattr {}'.format(filename))[0].split(' ')[0]
        else:
            s_name = os.path.basename(filename)
            s_path = os.path.dirname(filename)

            try:
                res = public.ExecShell('lsattr {}'.format(s_path))[0].strip()
                for s in res.split('\n'):
                    if not s: continue
                    lsattr_info = s.split()
                    if not lsattr_info: continue
                    if filename == lsattr_info[1]:
                        return lsattr_info[0]
            except:
                raise public.PanelError(lsattr_info)

        return '--------------e----'


    # 取指定文件属性
    def get_file_attribute(self,args):
        filename = args.filename.strip()
        if not os.path.exists(filename):
            return public.returnMsg(False,'the specified file does not exist!')
        attribute = {}
        attribute['name'] = os.path.basename(filename)
        attribute['path'] = os.path.dirname(filename)
        f_stat = os.stat(filename)
        attribute['st_atime'] = int(f_stat.st_atime)   # 最后访问时间
        attribute['st_mtime'] = int(f_stat.st_mtime)   # 最后修改时间
        attribute['st_ctime'] = int(f_stat.st_ctime)   # 元数据修改时间/权限或数据者变更时间
        attribute['st_size'] = f_stat.st_size          # 文件大小(bytes)
        attribute['st_gid'] = f_stat.st_gid            # 用户组id
        attribute['st_uid'] = f_stat.st_uid            # 用户id
        attribute['st_nlink'] = f_stat.st_nlink        #  inode 的链接数
        attribute['st_ino'] = f_stat.st_ino            #  inode 的节点号
        attribute['st_mode'] = f_stat.st_mode          #  inode 保护模式
        attribute['st_dev'] = f_stat.st_dev            #  inode 驻留设备
        attribute['user'] = self.get_mode_user(f_stat.st_uid)   # 所属用户
        attribute['group'] = self.get_mode_user(f_stat.st_gid)  # 所属组
        attribute['mode'] = str(oct(f_stat.st_mode)[-3:])         # 文件权限号
        attribute['md5'] = 'Do not count files or directories larger than 100MB'                        # 文件MD5
        attribute['sha1'] = 'Do not count files or directories larger than 100MB'                       # 文件sha1
        attribute['lsattr'] = self.get_lsattr(filename)
        attribute['is_dir'] = os.path.isdir(filename)   # 是否为目录
        attribute['is_link'] = os.path.islink(filename)  # 是否为链接文件
        if attribute['is_link']:
            attribute['st_type'] = 'Link file'
        elif attribute['is_dir']:
            attribute['st_type'] = 'Dir'
        else:
             attribute['st_type'] = self.get_file_ext(filename)
        attribute['history'] = []
        if f_stat.st_size < 104857600 and not attribute['is_dir']:
            hash_info = self.get_file_hash(filename=filename)
            attribute['md5'] = hash_info['md5']
            attribute['sha1'] = hash_info['sha1']
            attribute['history'] = self.get_history_info(filename) # 历史文件
        return attribute

    # 数据库对象
    def _get_sqlite_connect(self):
        try:
            if not self.sqlite_connection:
                self.sqlite_connection = sqlite3.connect('data/file_permissions.db')
        except Exception as ex:
            return "error: " + str(ex)

    # 操作数据库
    def _operate_db(self,q_sql,permissions_tb=None):
        try:
            self._get_sqlite_connect()
            c = self.sqlite_connection.cursor()
            table = "index_tb"
            if permissions_tb:
                table = permissions_tb
            sql_data = q_sql.replace("TB_NAME",table)
            return c.execute(sql_data)
        except:
            self._create_index_tb()
            self._operate_db(q_sql,permissions_tb)

    # 判断文件个数
    def _get_file_total(self,path,num,date):
        n = 0
        for p in os.listdir(path):
            full_path = path + "/" + p
            if os.path.isfile(full_path):
                if n == 0:
                    first_file = full_path
                n+=1
            if n >= num:
                self.path_permission_exclude_list.append(path)
                f_p = public.get_mode_and_user(path)
                data = {'path':first_file,'owner':f_p['user'],'mode':f_p['mode'],'type':'first_file','date':date}
                self.path_permission_list.append(data)
                return n

    # 创建权限表
    def _create_permissions_tb(self,tb_name):
        self._get_sqlite_connect()
        sql="""
CREATE TABLE {}(
   id INTEGER  PRIMARY KEY AUTOINCREMENT,
   path CHAR ,
   owner CHAR,
   mode CHAR,
   date CHAR,
   type CHAR 
);""".format(tb_name)
        self.sqlite_connection.execute(sql)

    def _create_index_tb(self):
        self._get_sqlite_connect()
        sql = """
CREATE TABLE index_tb(
   id INTEGER  PRIMARY KEY AUTOINCREMENT,
   permissions_tb CHAR ,
   date CHAR,
   remark CHAR,
   first_path CHAR
);"""
        self.sqlite_connection.execute(sql)

    # 获取权限表名
    def _get_permissions_tb_name(self,get_all_tb=None):
        sql = 'select permissions_tb from TB_NAME'
        data = self._operate_db(sql).fetchall()
        exist_tb = [i[0] for i in data]
        if get_all_tb:
            return exist_tb
        tb_names = ['p_tb'+str(x) for x in range(100)]
        tb_name = []
        if exist_tb:
            for n_tb in tb_names:
                if n_tb not in exist_tb:
                    tb_name.append(n_tb)
                    print(tb_name)
                    break
        if not tb_name:
            tb_name.append(tb_names[0])
        self._create_permissions_tb(tb_name[0])
        return tb_name[0]

    # 写入索引表
    def _write_index_tb(self,remark,date,tb_name,path):
        ins_sql = "INSERT INTO TB_NAME (remark,date,permissions_tb,first_path) VALUES ('{}', '{}', '{}','{}')".format(remark,date, tb_name,path)
        self._operate_db(ins_sql)
        self.sqlite_connection.commit()

    # 写入权限表
    def _write_permisssions_tb(self,tb_name):
        p_p_l = self.path_permission_list
        n = 0
        for p_p in p_p_l:
            ins_sql = "INSERT INTO TB_NAME (path,owner,mode,date,type) VALUES ('{}', '{}', '{}','{}','{}')".format(p_p['path'], p_p['owner'], p_p['mode'],p_p['date'],p_p['type'])
            self._operate_db(ins_sql,permissions_tb=tb_name)
            n += 1
            if n >= 1000:
                self.sqlite_connection.commit()
                n = 0
        self.sqlite_connection.commit()

    # 备份路径权限
    def _back_path_permissions (self,path,date):
        for p in os.listdir(path):
            full_p = path + "/" + p
            if os.path.isdir(full_p):
                # 如果文件夹下数量大于500添加文件夹到排除列表，权限只记录第一个文件的权限
                if self._get_file_total(full_p,500,date):
                    permission_type = "exclude_dir"
                else:
                    permission_type = "dir"
                f_p = public.get_mode_and_user(full_p)
                self.path_permission_list.append({'path':full_p,'owner':f_p['user'],'mode':f_p['mode'],'type':permission_type,'date':date})
                self._back_path_permissions(full_p,date)
                continue
            if path in self.path_permission_exclude_list:
                continue
            f_p = public.get_mode_and_user(full_p)
            data = {'path':full_p,'owner':f_p['user'], 'mode':f_p['mode'], 'type':'file','date':date}
            self.path_permission_list.append(data)

    # 备份目录权限
    def back_dir_perm(self,path,back_sub_dir,date,remark,tb_name):
        print("开始备份目录权限 {}".format(path))
        self._write_index_tb(remark,date,tb_name,path)
        f_p = public.get_mode_and_user(path)
        data = {'path':path,'owner':f_p["user"],'mode':f_p['mode'],'date':date,'type':'dir'}
        self.path_permission_list.append(data)
        if back_sub_dir == "0":
            self._write_permisssions_tb(tb_name)
            return True
        self._back_path_permissions(path, date)
        self._write_permisssions_tb(tb_name)

    # 备份单个文件权限
    def back_single_file_perm(self,path,date,remark,tb_name):
        print("开始备份文件权限 {}".format(path))
        self._write_index_tb(remark, date, tb_name,path)
        f_p = public.get_mode_and_user(path)
        data = {'path': path, 'owner': f_p["user"], 'mode': f_p['mode'], 'date': date, 'type': 'file'}
        self.path_permission_list.append(data)
        self._write_permisssions_tb(tb_name)

    # 备份权限
    def back_path_permissions(self,get):
        back_limit = 100
        if self._get_total_back() >= back_limit:
            return public.returnMsg(False,"The number of backup versions has exceeded {} ,Please go to the upper right corner [Backup Permissions] to clean up the old backup before operating".format(back_limit))
        if not os.path.exists(get.path):
            return public.returnMsg(False,"Path is incorrect {}".format(get.path))
        path = get.path
        back_sub_dir = get.back_sub_dir
        remark = get.remark
        self.path_permission_list = list()
        # self.file_permission_list = list()
        self.path_permission_exclude_list = list()
        date = int(time.time())
        tb_name = self._get_permissions_tb_name()
        try:
            if os.path.isdir(path):
                self.back_dir_perm(path,back_sub_dir,date,remark,tb_name)
            else:
                self.back_single_file_perm(path,date,remark,tb_name)
        except Exception as e:
            return public.returnMsg(False,"Backup error {} ".format(e))
        finally:
            self.sqlite_connection.commit()
        self.sqlite_connection.close()
        self.sqlite_connection=None
        return public.returnMsg(True,"Backup succeeded")

    # 获取所有需要还原文件和文件夹
    def _get_restore_file(self,path):
        for p in os.listdir(path):
            full_p = path + "/" + p
            if os.path.isdir(full_p):
                self.file_permission_list.append(full_p)
                self._get_restore_file(full_p)
                continue
            self.file_permission_list.append(full_p)

    # 直接递归还原目录下的文件权限
    def _recursive_restore_file_perm(self,path,p_i):
        file_permissions = self._operate_db(
            "SELECT owner,mode from TB_NAME where pid='{}' and type='{}'".format(p_i[0], 'first_file'),
            'file').fetchall()
        f_p = file_permissions[0]
        for i in os.listdir(path):
            i = "{}/{}".format(path, i)
            if os.path.isfile(i):
                public.set_mode(i, f_p[1])
                public.set_own(i, f_p[0])

    # 还原子目录权限
    def _restore_subdir_perm(self,path,date):
        path_info = self._operate_db("SELECT id,owner,mode,type from TB_NAME where path='{}' and date='{}'".format(path,date),
                                     'path').fetchall()
        p_i = path_info[0]
        public.set_mode(path, p_i[2])
        public.set_own(path, p_i[1])
        if p_i[3] == "exclude_dir":
            self._recursive_restore_file_perm(path,p_i)
        file_permissions = self._operate_db("SELECT path,owner,mode from TB_NAME where pid='{}' and date='{}'".format(p_i[0],date),
                                            'file').fetchall()
        if file_permissions:
            for f in file_permissions:
                if f[0] == ".user.ini":
                    continue
                file_path = "{}/{}".format(path, f[0])
                public.set_mode(file_path, f[2])
                public.set_own(file_path, f[1])

    # 还原目录权限
    def _restore_dir_perm(self,path_full,restore_sub_dir,date):
        tb_name = self._operate_db("select permissions_tb from TB_NAME where date='{}'".format(date)).fetchall()
        main_dir_data = self._operate_db("select path,owner,mode from TB_NAME where path='{}'".format(path_full),permissions_tb=tb_name[0][0]).fetchall()
        print(main_dir_data)
        if main_dir_data:
            public.set_mode(main_dir_data[0][0], main_dir_data[0][2])
            public.set_own(main_dir_data[0][0], main_dir_data[0][1])
        if restore_sub_dir == "0":
            print(main_dir_data[0][0])
            public.returnMsg(True, "Permission restored successfully")
        self._get_restore_file(path_full)
        if tb_name:
            data = self._operate_db("select path,owner,mode from TB_NAME",permissions_tb=tb_name[0][0]).fetchall()
            for d in data:
                if '.user.ini' in d[0]:
                    continue
                if d[0] in self.file_permission_list:
                    public.set_mode(d[0], d[2])
                    public.set_own(d[0], d[1])
        return public.returnMsg(True, "Permission restored successfully")

    # 还原单个文件权限
    def restore_single_file_perm(self,path_full,date):
        tb_name = self._operate_db("select permissions_tb from TB_NAME where date='{}'".format(date)).fetchall()
        main_dir_data = self._operate_db("select path,owner,mode from TB_NAME where path='{}'".format(path_full),permissions_tb=tb_name[0][0]).fetchall()
        if main_dir_data:
            public.set_mode(main_dir_data[0][0], main_dir_data[0][2])
            public.set_own(main_dir_data[0][0], main_dir_data[0][1])
            return public.returnMsg(True, "Permission restored successfully")
        return public.returnMsg(False, "The file does not have backup permissions")


    # 还原权限
    def restore_path_permissions(self,get):
        self.file_permission_list = list()
        path_full = get.path
        restore_sub_dir = get.restore_sub_dir
        date = get.date
        try:
            if os.path.isdir(path_full):
                result = self._restore_dir_perm(path_full,restore_sub_dir,date)
            else:
                result = self.restore_single_file_perm(path_full,date)
            return result
        finally:
            self.sqlite_connection.close()
            self.sqlite_connection = None


    def get_path_premissions(self,get):
        path_full = get.path
        result = []
        exist_tbs = self._get_permissions_tb_name(get_all_tb=True)
        for tb_name in exist_tbs:
            data = self._operate_db("select path,owner,mode,date from TB_NAME where path='{}'".format(path_full),
                             permissions_tb=tb_name).fetchall()
            if data:
                index_data = self._operate_db("select id,remark from index_tb where permissions_tb='{}'".format(tb_name)).fetchall()
                d_l = []
                for i in data[0]:
                    d_l.append(i)
                if index_data:
                    d_l.append(index_data[0][1])
                    d_l.append(index_data[0][0])
                result.append(d_l)
        return sorted(result,key=lambda x:x[3],reverse=True)

    def del_path_premissions(self,get):
        p_tb = self._operate_db("select permissions_tb from index_tb where id='{}'".format(get.id)).fetchall()
        # 删除引导行
        self._operate_db("delete from index_tb where id='{}'".format(get.id)).fetchall()
        if p_tb:
            self._operate_db("drop table '{}'".format(p_tb[0][0]))
        self.sqlite_connection.commit()
        self.sqlite_connection.close()
        return public.returnMsg(True, "successfully deleted")

    # 获取所有备份
    def get_all_back(self,get):
        data = self._operate_db('select id,remark,date,first_path from index_tb').fetchall()
        return sorted(data,key=lambda x: x[2],reverse=True)

    def _get_total_back(self):
        data = self._operate_db('select id from index_tb').fetchall()
        return len(data)

    # 一键恢复默认权限
    def fix_permissions(self,get):
        if not hasattr(get,"uid"):
            import pwd
            get.uid = pwd.getpwnam('www').pw_uid
            get.gid = pwd.getpwnam('www').pw_gid
        path = get.path
        if os.path.isfile(path):
            os.chown(path, get.uid, get.gid)
            os.chmod(path, 0o644)
            return public.returnMsg(True, "Permission repair succeeded")
        os.chown(path, get.uid, get.gid)
        os.chmod(path, 0o755)
        for file in os.listdir(path):
            try:
                filename = os.path.join(path,file)
                os.chown(filename, get.uid, get.gid)
                if os.path.isdir(filename):
                    os.chmod(filename, 0o755)
                    get.path = filename
                    self.fix_permissions(get)
                    continue
                os.chmod(filename,0o644)
            except:
                print(public.get_error_info())
        return public.returnMsg(True,"Permission repair succeeded")

    def restore_website(self,args):
        """
            @name 恢复站点文件
            @author zhwen<zhw@bt.cn>
            @parma file_name 备份得文件名
            @parma site_id 网站id
        """
        import panel_restore
        pr=panel_restore.panel_restore()
        return pr.restore_website_backup(args)

    def get_progress(self,args):
        """
            @name 获取进度日志
            @author zhwen<zhw@bt.cn>
        """
        import panel_restore
        pr=panel_restore.panel_restore()
        return pr.get_progress(args)