#!/usr/bin/python3
# coding: utf-8
import utils as u
from data import data as data_init
from flask import Flask, render_template, request, url_for, redirect, flash, make_response
from markupsafe import escape


d = data_init()
app = Flask(__name__)

# ---


def reterr(code, message):
    ret = {
        'success': False,
        'code': code,
        'message': message
    }
    u.error(f'{code} - {message}')
    return u.format_dict(ret)


def showip(req, msg):
    ip1 = req.remote_addr
    try:
        ip2 = req.headers['X-Forwarded-For']
        u.infon(f'- Request: {ip1} / {ip2} : {msg}')
    except:
        ip2 = None
        u.infon(f'- Request: {ip1} : {msg}')

DEFAULT_SLACK_APPS = [
    'bilibili', '哔哩哔哩', 'youtube', '抖音', 'tiktok', '微博', '小红书', '知乎',
    'netflix', '爱奇艺', '腾讯视频', '优酷', 'steam', 'epic games', 'minecraft',
    '网易云音乐', 'spotify', 'qq音乐', '游戏'
]
DEFAULT_WORK_APPS = [
    'xcode', 'visual studio code', 'code', '终端', 'terminal', 'iterm2',
    'intellij idea', 'pycharm', 'webstorm', 'goland', 'sublime text', 'nova',
    'pages', 'numbers', 'keynote', 'microsoft word', 'word', 'microsoft excel',
    'excel', 'microsoft powerpoint', 'powerpoint', '飞书', '钉钉', 'slack',
    'notion', 'obsidian', 'figma', 'sketch', 'docker', 'postman'
]


def _match_app(app, names):
    app_l = app.lower()
    return any(app_l == str(n).lower() for n in names)


def pc_display():
    """根据 pc_status / pc_app_name 计算电脑端展示信息。"""
    app = (d.data.get('pc_app_name') or '').strip()
    pc_st = d.data.get('pc_status', 0)
    try:
        stlist = d.data['status_list']
    except Exception:
        stlist = []
    if pc_st != 0:
        try:
            info = stlist[pc_st].copy()
        except Exception:
            info = {'name': '未知', 'desc': '未知的标识符，可能是配置问题。', 'color': 'error'}
        return info
    if not app:
        return {'name': '系统桌面', 'desc': '目前 Mac 上暂无前台应用。', 'color': 'awake'}
    if _match_app(app, d.data.get('pc_slack_apps', DEFAULT_SLACK_APPS)):
        return {'name': app, 'desc': f'目前 Mac 上正在使用 {app}，大概率在摸鱼。', 'color': 'slacking'}
    if _match_app(app, d.data.get('pc_work_apps', DEFAULT_WORK_APPS)):
        return {'name': app, 'desc': f'目前 Mac 上正在使用 {app}，在认真工作。', 'color': 'working'}
    return {'name': app, 'desc': f'目前 Mac 上正在使用 {app}。', 'color': 'awake'}


@app.route('/')
def index():
    d.load()
    showip(request, '/')
    ot = d.data['other']
    try:
        stat = d.data['status_list'][d.data['status']].copy()
        if d.data['status'] == 0:
            stat['name'] = d.data.get('app_name', stat.get('name'))
    except:
        stat = {
            'name': '未知',
            'desc': '未知的标识符，可能是配置问题。',
            'color': 'error'
        }
    pc_stat = pc_display()
    return render_template(
        'index.html',
        user=ot['user'],
        learn_more=ot['learn_more'],
        repo=ot['repo'],
        status_name=stat['name'],
        status_desc=stat['desc'],
        pc_status_name=pc_stat['name'],
        pc_status_desc=pc_stat['desc'],
        status_color=stat['color'],
        pc_status_color=pc_stat['color'],
        more_text=ot['more_text']
    )


@app.route('/style.css')
def style_css():
    response = make_response(render_template(
        'style.css',
        bg=d.data['other']['background'],
        alpha=d.data['other']['alpha']
    ))
    response.mimetype = 'text/css'
    return response


@app.route('/query')
def query():
    d.load()
    showip(request, '/query')
    st = d.data.get('status', 0)
    try:
        stinfo = d.data['status_list'][st].copy()
        if st == 0:
            stinfo['name'] = d.data.get('app_name', stinfo.get('name'))
    except Exception:
        stinfo = {
            'status': st,
            'name': '未知',
            'desc': '',
            'color': ''
        }
    # 电脑端状态（含摸鱼判断）
    pc_info = pc_display()
    ret = {
        'success': True,
        'status': st,
        'info': stinfo,
        'pc_status': d.data.get('pc_status', 0),
        'pc_info': pc_info
    }
    return u.format_dict(ret)


@app.route('/get/status_list')
def get_status_list():
    showip(request, '/get/status_list')
    stlst = d.dget('status_list')
    return u.format_dict(stlst)


@app.route('/set')
def set_normal():
    showip(request, '/set')
    status = escape(request.args.get("status"))
    app_name = escape(request.args.get("app_name"))
    if not status.isdigit():
        status = None
    if app_name == "" or app_name == "None":
        app_name = None
    pc_status = escape(request.args.get("pc_status"))
    pc_app_name = escape(request.args.get("pc_app_name"))
    if not pc_status.isdigit():
        pc_status = None
    if pc_app_name == "" or pc_app_name == "None":
        pc_app_name = None
    secret = escape(request.args.get("secret"))
    secret_masked = f'{str(secret)[:2]}***' if secret else ''
    u.info(f'status: {status}, name: {app_name}, secret: "{secret_masked}", pc_status: {pc_status}, pc_name: {pc_app_name}')
    print(f'status: {status}, name: {app_name}, secret: "{secret_masked}", pc_status: {pc_status}, pc_name: {pc_app_name}')
    secret_real = d.dget('secret')
    if secret == secret_real:
        if status is not None:
            d.dset('status', int(status))
        if app_name is not None:
            d.dset('app_name', app_name)
        if pc_status is not None:
            d.dset('pc_status', int(pc_status))
        if pc_app_name is not None:
            d.dset('pc_app_name', pc_app_name)
        u.info('set success')
        ret = {
            'success': True,
            'code': 'OK',
            'set_to': status,
            'app_name':app_name,
            'pc_set_to': pc_status,
            'pc_app_name': pc_app_name
        }
        return u.format_dict(ret)
    else:
        return reterr(
            code='not authorized',
            message='invaild secret'
        )



if __name__ == '__main__':
    d.load()
    app.run(
        host=d.data['host'],
        port=d.data['port'],
        debug=d.data['debug']
    )
