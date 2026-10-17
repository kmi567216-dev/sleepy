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

@app.route('/')
def index():
    d.load()
    showip(request, '/')
    ot = d.data['other']
    try:
        stat = d.data['status_list'][d.data['status']].copy()
        pc_stat = d.data['status_list'][d.data['pc_status']].copy()
        if(d.data['pc_status'] == 0):
            pc_app_name = d.data['pc_app_name']
            pc_stat['name'] = pc_app_name
        if(d.data['status'] == 0):
            app_name = d.data['app_name']
            stat['name'] = app_name
    except:
        stat = {
            'name': '未知',
            'desc': '未知的标识符，可能是配置问题。',
            'color': 'error'
        }
        pc_stat = dict(stat)
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
    st = d.data['status']
    # stlst = d.data['status_list']
    try:
        stinfo = d.data['status_list'][st]
        if(st == 0):
            stinfo['name'] = d.data['app_name']
    except:
        stinfo = {
            'status': st,
            'name': '未知'
        }
    ret = {
        'success': True,
        'status': st,
        'info': stinfo
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
