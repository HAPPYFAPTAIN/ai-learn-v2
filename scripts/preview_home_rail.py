"""Render the real home rail with Gradio, using no accounts, models or learning data."""
import argparse
import ast
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import gradio as gr
from fastapi import FastAPI
from fastapi.responses import Response
import uvicorn
from learning_ext.presentation import ASSETS,presentation_css


def rail_html():
    tree=ast.parse((ROOT/'learning_ext/home_rail.py').read_text())
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in {'_start_card','_links_card'}]
    namespace={}
    exec(compile(ast.Module(body=functions,type_ignores=[]),'home_rail.py','exec'),namespace)
    return '<aside class="le-rail" aria-label="学习概览">'+namespace['_start_card']()+namespace['_links_card'](0)+'</aside>'


def stylesheet():
    order=('theme_tokens.css','shell.css','assistant.css','text_polish.css','theme_toggle.css')
    return '\n'.join((ASSETS/name).read_text() for name in order)+'\n'+presentation_css()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=7863)
    args=parser.parse_args()
    with gr.Blocks(head='<link rel="stylesheet" href="/le-presentation.css">',analytics_enabled=False) as demo:
        with gr.Tabs(elem_id='le-app-tabs'):
            with gr.Tab('学习首页',elem_id='learning-guide-tab'):
                with gr.Column(elem_id='le-guided-home'):
                    with gr.Row(elem_id='le-home-wide'):
                        with gr.Column(elem_id='le-home-main'):
                            gr.HTML('<h1>学习首页布局验证</h1><p>此页面只渲染原组件，没有用户数据或模型调用。</p>')
                        with gr.Column(elem_id='le-home-rail'):
                            gr.HTML(rail_html())
    app=FastAPI()
    @app.get('/le-presentation.css')
    def css():return Response(stylesheet(),media_type='text/css',headers={'Cache-Control':'no-store'})
    app=gr.mount_gradio_app(app,demo,path='/')
    uvicorn.run(app,host='127.0.0.1',port=args.port)


if __name__=='__main__':main()
