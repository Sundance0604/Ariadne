"""Unified local caption editor: choose a project, edit text/styles and export."""
import argparse
import copy
import json
import os
from pathlib import Path
import queue
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.video_export.content import read, write
from backend.video_export.presentation import presentation_config
from backend.video_export.editor import (DOCUMENT, PACKAGE, SLOTS, STYLE_FIELDS, package_config, validate_style, export, load_document, prepare,
    column_key, document_names, normalized_sizes, stored_column, stored_sizes)
from backend.video_export.paths import configured_path,full_paths,editor_projects,settings


def resolve_target(args):
    """CLI overrides never pair a custom package with another project's draft."""
    if args.project:
        project=next((p for p in editor_projects() if p['id']==args.project),None)
        if project is None:raise ValueError('未知字幕项目：'+args.project)
        package,document=project['package'],project['document']
    elif args.full:
        package,document=full_paths()
    else:
        package,document=PACKAGE,DOCUMENT
    if args.package:
        package=args.package.resolve()
        document=package/'captions-editable.json'
    if args.document:document=args.document.resolve()
    return package,document


def choose_project(root):
    """Selecting or cancelling only reads paths; it never creates a document."""
    import tkinter as tk
    from tkinter import ttk,messagebox
    projects=editor_projects()
    dialog=tk.Toplevel(root)
    dialog.title('选择字幕项目')
    dialog.geometry('780x340')
    dialog.minsize(640,300)
    outer=ttk.Frame(dialog,padding=20);outer.pack(fill='both',expand=True)
    ttk.Label(outer,text='选择要编辑的视频',font=('Microsoft YaHei UI',14)).pack(anchor='w',pady=(0,12))
    default=settings().get('editor_default_project')
    selected=tk.StringVar(value=next((p['id'] for p in projects if p['id']==default),projects[0]['id']))
    for project in projects:
        ttk.Radiobutton(outer,text=project['title'],variable=selected,value=project['id']).pack(anchor='w',pady=5)
    detail=tk.StringVar()
    def describe(*_):
        project=next(p for p in projects if p['id']==selected.get())
        detail.set('文稿：'+project['document'].relative_to(ROOT).as_posix()+'\n资源包：'+project['package'].relative_to(ROOT).as_posix())
    selected.trace_add('write',describe);describe()
    ttk.Label(outer,textvariable=detail,wraplength=720).pack(anchor='w',pady=14)
    result=[]
    def open_selected():
        project=next(p for p in projects if p['id']==selected.get())
        package=project['package']
        if not project['document'].is_file() or not any((package/name).is_file() for name in ('export-config.json','export-config-kaiti.json')):
            messagebox.showerror('本地资料未齐备','这个项目需要已有字幕文稿和本地视频资源包。请先准备对应资料，再打开编辑。',parent=dialog)
            return
        result.append((project['package'],project['document']))
        dialog.destroy()
    buttons=ttk.Frame(outer);buttons.pack(fill='x',side='bottom')
    def open_panels():result.append('panels');dialog.destroy()
    ttk.Button(buttons,text='和声／配器面板设置',command=open_panels).pack(side='left')
    ttk.Button(buttons,text='打开编辑器',command=open_selected).pack(side='right')
    ttk.Button(buttons,text='取消',command=dialog.destroy).pack(side='right',padx=8)
    dialog.bind('<Return>',lambda _:open_selected())
    dialog.bind('<Escape>',lambda _:dialog.destroy())
    dialog.protocol('WM_DELETE_WINDOW',dialog.destroy)
    root.wait_window(dialog)
    return result[0] if result else None


class PanelEditor:
    """Visual settings in the existing editor, never a second subtitle editor."""
    def __init__(self,root):
        import tkinter as tk
        from tkinter import ttk,messagebox,colorchooser
        from backend.video_export.visual_panels import load_settings,part_registry,panel_layout
        self.root=root;self.tk=tk;self.ttk=ttk;self.messagebox=messagebox;self.colorchooser=colorchooser
        self.value=load_settings();self.busy=False;self.result=None;self.messages=queue.Queue()
        registry_doc=read(configured_path('visual_parts'));self.parts=registry_doc['parts'];self.flow_groups=registry_doc.get('harmony_groups')
        root.title('普罗第二钢协 · 和声与配器面板');root.geometry('880x790');root.minsize(780,720)
        body=ttk.Frame(root,padding=20);body.pack(fill='both',expand=True)
        ttk.Label(body,text='和声瀑布图与配器激活',font=('Microsoft YaHei UI',16)).pack(anchor='w')
        ttk.Label(body,text='和声图按五类配色，配器面板逐件激活；大小与颜色分别设置，复用现有同步。').pack(anchor='w',pady=(8,16))
        controls=ttk.Frame(body);controls.pack(fill='x');self.scales={};self.enabled={};self.dimensions={}
        sizes=panel_layout({},parts=part_registry(self.parts),flow_groups=self.flow_groups);orchestra_size=sizes['panels']['orchestration'];flow_size=sizes['panels']['flow']
        for row,(key,label,w,h) in enumerate([('flow','和声瀑布图',flow_size['width'],flow_size['height']),('orchestration','配器激活面板',orchestra_size['width'],orchestra_size['height'])]):
            self.enabled[key]=tk.BooleanVar(value=self.value[key]['enabled']);self.scales[key]=tk.IntVar(value=round(self.value[key]['scale']*100))
            ttk.Checkbutton(controls,text=label,variable=self.enabled[key]).grid(row=row,column=0,sticky='w',padx=(0,16),pady=8)
            ttk.Spinbox(controls,from_=60,to=150,increment=5,textvariable=self.scales[key],width=7).grid(row=row,column=1)
            ttk.Label(controls,text='%').grid(row=row,column=2,padx=8)
            self.dimensions[key]=tk.StringVar();ttk.Label(controls,textvariable=self.dimensions[key]).grid(row=row,column=3,sticky='w')
            self.scales[key].trace_add('write',lambda *_,k=key,bw=w,bh=h:self.dimension(k,bw,bh));self.dimension(key,w,h)
        self.clip=tk.StringVar(value='全奏 · 10:15起，含打击乐' if self.value['sample_start']==615 else '抒情 · 01:31起')
        clips=ttk.Frame(body);clips.pack(fill='x',pady=12)
        ttk.Label(clips,text='45秒样片片段：').pack(side='left')
        ttk.Combobox(clips,state='readonly',textvariable=self.clip,values=['全奏 · 10:15起，含打击乐','抒情 · 01:31起'],width=30).pack(side='left')
        ttk.Label(body,text='和声五类颜色／配器逐件颜色').pack(anchor='w',pady=(8,6))
        tree_frame=ttk.Frame(body);tree_frame.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(tree_frame,columns=('family','color'),height=16,selectmode='browse')
        self.tree.heading('#0',text='乐器模块');self.tree.heading('family',text='分组');self.tree.heading('color',text='颜色')
        self.tree.column('#0',width=330);self.tree.column('family',width=170);self.tree.column('color',width=160)
        scrollbar=ttk.Scrollbar(tree_frame,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y');self.tree.pack(side='left',fill='both',expand=True)
        row=ttk.Frame(body);row.pack(fill='x',pady=9)
        ttk.Button(row,text='更改所选乐器颜色',command=self.change_color).pack(side='left')
        ttk.Button(row,text='恢复高区分配色与默认大小',command=self.defaults).pack(side='left',padx=10)
        self.status=tk.StringVar(value='设置用于普二样片及完整版；保存后在对应项目生成新视频时生效，已有视频保留。')
        ttk.Label(body,textvariable=self.status,wraplength=810).pack(anchor='w',pady=6)
        self.percent=tk.DoubleVar();ttk.Progressbar(body,variable=self.percent,maximum=100).pack(fill='x',pady=5)
        buttons=ttk.Frame(body);buttons.pack(fill='x',pady=(8,0))
        self.save_button=ttk.Button(buttons,text='保存设置',command=self.save);self.save_button.pack(side='left')
        self.render_button=ttk.Button(buttons,text='保存并生成45秒样片',command=self.render);self.render_button.pack(side='left',padx=10)
        ttk.Button(buttons,text='打开最近样片',command=self.open_latest).pack(side='right')
        self.refresh_colors();root.after(150,self.poll)

    def dimension(self,key,w,h):
        try:self.dimensions[key].set(f'{round(w*self.scales[key].get()/100)} × {round(h*self.scales[key].get()/100)} 像素')
        except Exception:self.dimensions[key].set('请输入60至150')

    def refresh_colors(self):
        from backend.video_export.visual_panels import part_registry
        self.tree.delete(*self.tree.get_children())
        if self.flow_groups:
            self.tree.insert('','end',iid='flow-root',text='和声图 · 五类',open=True)
            for g in self.flow_groups:
                identity='flow:'+g['id'];color=self.value['group_colors'].get(g['id'],g['color'])
                self.tree.insert('flow-root','end',iid=identity,text=g['label'],values=('和声分类',color),tags=(identity,))
                self.tree.tag_configure(identity,foreground=color,background='#18160e')
        self.tree.insert('','end',iid='instrument-root',text='配器 · 乐器模块',open=True)
        for p in part_registry(self.parts,colors=self.value['part_colors']):
            self.tree.insert('instrument-root', 'end',iid=p['id'],text=('独奏 · ' if p['role']=='solo' else '')+p['label'],
                values=(p['family'],p['color']),tags=(p['id'],));self.tree.tag_configure(p['id'],foreground=p['color'],background='#18160e')

    def change_color(self):
        if self.busy:return
        selection=self.tree.selection()
        if not selection:return
        pid=selection[0]
        if pid in ('flow-root','instrument-root'):return
        current=self.tree.item(pid,'values')[1]
        color=self.colorchooser.askcolor(color=current,title='选择声部颜色',parent=self.root)[1]
        if color:
            if pid.startswith('flow:'):self.value['group_colors'][pid[5:]]=color
            else:self.value['part_colors'][pid]=color
            self.refresh_colors();self.tree.selection_set(pid)

    def defaults(self):
        if self.busy:return
        from backend.video_export.visual_panels import DEFAULTS
        self.value=copy.deepcopy(DEFAULTS)
        for key in self.scales:self.scales[key].set(100);self.enabled[key].set(True)
        self.clip.set('全奏 · 10:15起，含打击乐');self.refresh_colors()

    def save(self):
        from backend.video_export.visual_panels import save_settings
        try:
            value=copy.deepcopy(self.value)
            for key in self.scales:value[key]={'enabled':self.enabled[key].get(),'scale':self.scales[key].get()/100}
            value['sample_start']=615.0 if self.clip.get().startswith('全奏') else 91.4
            self.value=save_settings(value);self.status.set('设置已保存；生成新样片时生效。');return True
        except Exception as error:self.messagebox.showerror('设置无效',str(error),parent=self.root);return False

    def render(self):
        if self.busy or not self.save():return
        self.busy=True;self.save_button.configure(state='disabled');self.render_button.configure(state='disabled');snapshot=copy.deepcopy(self.value)
        def worker():
            try:self.messages.put(('done',render_visual_sample(snapshot,lambda p,m:self.messages.put(('progress',p,m)))))
            except Exception as error:self.messages.put(('error',str(error)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            while True:
                item=self.messages.get_nowait()
                if item[0]=='progress':self.percent.set(item[1]);self.status.set(item[2]);continue
                self.busy=False;self.save_button.configure(state='normal');self.render_button.configure(state='normal')
                if item[0]=='done':self.result=item[1];self.status.set('已生成：'+str(self.result))
                else:self.status.set('生成失败，已有样片保留。');self.messagebox.showerror('生成失败',item[1],parent=self.root)
        except queue.Empty:pass
        self.root.after(150,self.poll)

    def open_latest(self):
        pointer=configured_path('visual_latest')
        path=self.result or (ROOT/read(pointer)['path'] if pointer.exists() else None)
        if path and path.is_file():os.startfile(path)
        else:self.messagebox.showinfo('尚无样片','先保存并生成一个样片。',parent=self.root)


def render_visual_sample(value,progress=None):
    from backend.video_export.visual_panels import validate_settings
    from scripts.video_export.build_prokofiev2_flow_sample import build
    value=validate_settings(value);base=configured_path('visual_sample_root');index=1
    while (base/f'prokofiev2-visual-sample-{index:03d}').exists():index+=1
    path=build(base/f'prokofiev2-visual-sample-{index:03d}',start=value['sample_start'],panels=value,progress=progress)
    write(configured_path('visual_latest'),{'path':path.relative_to(ROOT).as_posix()})
    return path


def import_document(path, current, config):
    """Read a copy; saving an import must never overwrite the external source."""
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('请选择包含“字幕”数组的编辑JSON，或包含events数组的annotations.json。')
    if '字幕' not in data and isinstance(data.get('events'), list):
        rows = []
        reverse = {v:k for k,v in SLOTS.items()}
        offset = config['segments'][0]['video_start']
        for i, e in enumerate(data['events'], 1):
            if not isinstance(e, dict) or e.get('slot') not in reverse:
                raise ValueError(f'第{i}条events记录缺少有效的slot栏目。')
            label = '片头' if e.get('phase') == 'intro' else reverse[e['slot']]
            start = e['output_start'] if 'output_start' in e else float(e['video_start'])-offset if 'video_start' in e else None
            end = e['output_end'] if 'output_end' in e else float(e['video_end'])-offset if 'video_end' in e else None
            rows.append({'编号':e.get('id',f'import-{i}'), '栏目':label, '开始秒':start, '结束秒':end,
                         '文字':e.get('text'), '标题':e.get('display_title',''), '显示':True,
                         **({'研究条目':e['research_reading_id'],'关系依据':e.get('relation_ids',[])} if e.get('research_reading_id') else {})})
        data = {'字幕':rows}
    if not isinstance(data.get('字幕'), list):
        raise ValueError('这个JSON没有“字幕”数组或events数组，不能作为字幕载入。')
    sizes = data.get('字号', {})
    names = data.get('栏目名称', {})
    if not isinstance(sizes, dict) or not isinstance(names, dict):
        raise ValueError('“字号”和“栏目名称”必须为对象。')
    names = {**document_names(current), **document_names(data)}
    sizes = {**normalized_sizes(current['字号']), **normalized_sizes(sizes)}
    for label in SLOTS:
        if isinstance(sizes[label], bool) or not isinstance(sizes[label], int) or not 12 <= sizes[label] <= 120:
            raise ValueError(f'{label}字号请输入12至120的整数。')
    aliases = {v:k for k,v in names.items()}
    aliases.update({'声部关系与复调':'对位', '曲式与主题发展':'曲式'})
    for i, row in enumerate(data['字幕'], 1):
        if not isinstance(row, dict):
            raise ValueError(f'第{i}条字幕必须为对象。')
        key=column_key(aliases.get(row.get('栏目'),row.get('栏目')))
        if key not in SLOTS or not isinstance(row.get('文字'), str):
            raise ValueError(f'第{i}条字幕缺少有效的“栏目”或“文字”。')
        row['栏目']=stored_column(key,names)
        if any(row.get(k) is None or isinstance(row[k], (bool,dict,list)) for k in ('开始秒','结束秒')):
            raise ValueError(f'第{i}条字幕缺少可编辑的“开始秒”和“结束秒”。')
        if not isinstance(row.get('标题',''), str) or not isinstance(row.get('显示',True), bool):
            raise ValueError(f'第{i}条字幕的标题或显示格式不正确。')
        row.setdefault('编号', f'import-{i}')
        row.setdefault('显示', True)
    labels = [names.get(name,name) for name in SLOTS]
    if any(not isinstance(v,str) or not v.strip() for v in labels) or len(set(labels)) != len(labels):
        raise ValueError('栏目显示名称须为互不重复的非空文字。')
    return {**data, '字号':stored_sizes(sizes,names),
            '栏目名称':{stored_column(k,names):v for k,v in names.items()}, '导入来源':str(Path(path).resolve())}


class Editor:
    def __init__(self, root, package=PACKAGE, document=DOCUMENT, fonts=False):
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
        self.tk, self.ttk, self.messagebox = tk, ttk, messagebox
        self.filedialog = filedialog
        self.root, self.package, self.path = root, package, document
        self.data = load_document(document, package)
        self.names = {name:document_names(self.data).get(name,name) for name in SLOTS}
        self.internal_names = {label:name for name,label in self.names.items()}
        config = presentation_config(package_config(package),self.data.get('呈现规则',{}))
        self.config = config
        segment = config['segments'][0]
        duration = segment['video_end'] - segment['video_start']
        self.selected, self.busy, self.result = None, False, None
        self.dirty = False
        self.messages = queue.Queue()
        root.title('导聆视频 · 字幕编辑 · '+str(document.relative_to(ROOT) if document.is_relative_to(ROOT) else document))
        root.geometry('1160x850')
        root.minsize(900, 680)
        root.option_add('*Font', ('Microsoft YaHei UI', 11))
        root.protocol('WM_DELETE_WINDOW', self.close)
        outer = ttk.Frame(root, padding=14)
        outer.pack(fill='both', expand=True)
        top = ttk.Frame(outer)
        top.pack(fill='x')
        ttk.Label(top, text=f'修改当前{duration:g}秒视频的字幕；时间单位为成片秒数。').pack(side='left')
        self.import_button = ttk.Button(top,text='打开外部JSON…',command=self.open_external)
        self.import_button.pack(side='right')
        book = ttk.Notebook(outer)
        book.pack(fill='both', expand=True, pady=10)
        page, font_page = ttk.Frame(book, padding=10), ttk.Frame(book, padding=16)
        book.add(page, text='文字与出现时间')
        book.add(font_page, text='位置、字体与滚动')
        tools = ttk.Frame(page)
        tools.pack(fill='x')
        ttk.Label(tools, text='筛选栏目：').pack(side='left')
        self.filter = tk.StringVar(value='全部')
        picker = ttk.Combobox(tools, textvariable=self.filter, state='readonly', values=['全部', *self.names.values()], width=18)
        self.filter_picker = picker
        picker.pack(side='left')
        picker.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Button(tools, text='新增一条', command=self.add).pack(side='right')
        listing = ttk.Frame(page)
        listing.pack(fill='both', expand=True, pady=8)
        self.tree = ttk.Treeview(listing, columns=('show', 'slot', 'start', 'end', 'text'), show='headings', selectmode='browse', height=9)
        for name, label, width in [('show', '显示', 45), ('slot', '栏目', 70), ('start', '开始秒', 90), ('end', '结束秒', 90), ('text', '正文预览', 640)]:
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, stretch=name == 'text')
        if self.data.get('栏目名称'):
            self.tree.column('slot',width=155)
        bar = ttk.Scrollbar(listing, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', self.select)
        fields = ttk.Frame(page)
        fields.pack(fill='x')
        self.slot = tk.StringVar()
        self.start, self.end = tk.StringVar(), tk.StringVar()
        self.visible, self.title = tk.BooleanVar(value=True), tk.StringVar()
        ttk.Label(fields, text='栏目').grid(row=0, column=0, sticky='w')
        self.slot_picker = ttk.Combobox(fields, textvariable=self.slot, state='readonly', values=list(self.names.values()), width=18)
        self.slot_picker.grid(row=0, column=1, padx=(4, 16))
        ttk.Label(fields, text='开始秒').grid(row=0, column=2)
        ttk.Entry(fields, textvariable=self.start, width=12).grid(row=0, column=3, padx=(4, 16))
        ttk.Label(fields, text='结束秒').grid(row=0, column=4)
        ttk.Entry(fields, textvariable=self.end, width=12).grid(row=0, column=5, padx=(4, 16))
        ttk.Checkbutton(fields, text='显示此条（取消即隐藏）', variable=self.visible).grid(row=0, column=6)
        heading = ttk.Frame(page)
        heading.pack(fill='x', pady=(10, 4))
        ttk.Label(heading, text='自定义标题（留空使用栏目名）').pack(side='left')
        ttk.Entry(heading, textvariable=self.title).pack(side='left', fill='x', expand=True, padx=8)
        overrides=ttk.LabelFrame(page,text='此条字幕的单独样式（留空沿用栏目设置）',padding=5)
        overrides.pack(fill='x',pady=4)
        self.row_style={}
        for i,key in enumerate(STYLE_FIELDS):
            ttk.Label(overrides,text=key).grid(row=0,column=i,padx=4,sticky='w')
            var=tk.StringVar();var.trace_add('write',lambda *_:self.changed());self.row_style[key]=var
            ttk.Entry(overrides,textvariable=var,width=17 if key=='字体' else 9).grid(row=1,column=i,padx=4,sticky='w')
        ttk.Label(page, text='正文（可直接粘贴多行文字）').pack(anchor='w')
        body = ttk.Frame(page)
        body.pack(fill='both', expand=True, pady=(4, 8))
        self.text = tk.Text(body, wrap='word', height=7, undo=True, font=('KaiTi', 16))
        body_scroll = ttk.Scrollbar(body, command=self.text.yview)
        self.text.configure(yscrollcommand=body_scroll.set)
        self.text.pack(side='left', fill='both', expand=True)
        body_scroll.pack(side='right', fill='y')
        for variable in (self.slot, self.start, self.end, self.visible, self.title):
            variable.trace_add('write', lambda *_: self.changed())
        self.text.bind('<<Modified>>', self.text_changed)
        score_behavior='诠释显示时保留右侧谱面。' if config.get('interpretation_hides_score') is False else '诠释显示时乐谱自动隐藏，结束后恢复。'
        ttk.Label(page, text=f'片头须在{config.get("intro_clear_video",config["music_start_video"]-3):g}秒前结束；常规字幕从{config["music_start_video"]:g}秒开始。'+score_behavior, wraplength=1000).pack(anchor='w')
        self.fonts = {}
        self.font_labels = {}
        self.styles={}
        headers=['栏目','字号','横坐标','纵坐标','宽度','高度','字体','滚动倍速']
        for col,title in enumerate(headers):ttk.Label(font_page,text=title).grid(row=0,column=col,padx=7,sticky='w')
        for i, label in enumerate(SLOTS):
            self.font_labels[label] = ttk.Label(font_page,text=self.names[label])
            self.font_labels[label].grid(row=i+1, column=0, sticky='w', pady=10)
            var = tk.StringVar(value=str(normalized_sizes(self.data['字号'])[label]))
            var.trace_add('write', lambda *_: self.changed())
            self.fonts[label] = var
            ttk.Spinbox(font_page, from_=12, to=120, textvariable=var, width=6).grid(row=i+1, column=1, padx=7)
            self.styles[label]={}
            base=config['layout'][SLOTS[label]]
            saved=self.data.get('字幕样式',{}).get(stored_column(label,self.names),{})
            for col,key in enumerate(headers[2:],2):
                default=base.get(STYLE_FIELDS[key],config.get('font','KaiTi') if key=='字体' else config.get('scroll_speed',1) if key=='滚动倍速' else '')
                field=tk.StringVar(value=str(saved.get(key,default)));field.trace_add('write',lambda *_:self.changed())
                self.styles[label][key]=field
                ttk.Entry(font_page,textvariable=field,width=19 if key=='字体' else 7).grid(row=i+1,column=col,padx=5)
        ttk.Label(font_page,text='坐标以画面左上角为原点，单位为像素。滚动倍速1为原速，1.5快一半，2为两倍；只加快滚动，不改变字幕起止时间。\n单条例外可在“文字与出现时间”页签填写。字体可填系统已安装字体名，例如KaiTi、Microsoft YaHei。\n保存只更新JSON；生成新视频后设置才会出现在MP4中。',wraplength=1000).grid(row=8,column=0,columnspan=8,pady=24,sticky='w')
        actions = ttk.Frame(outer)
        actions.pack(fill='x')
        self.save_button = ttk.Button(actions, text='保存修改', command=self.save)
        self.save_button.pack(side='left')
        self.ass_button = ttk.Button(actions, text='仅导出ASS字幕', command=lambda: self.generate(True))
        self.ass_button.pack(side='left', padx=8)
        self.render_button = ttk.Button(actions, text='保存并生成新视频', command=self.generate)
        self.render_button.pack(side='left')
        self.open_button = ttk.Button(actions, text='打开最新视频', command=self.open_result)
        self.open_button.pack(side='right')
        ttk.Button(actions, text='打开输出文件夹', command=self.open_folder).pack(side='right', padx=8)
        self.percent = tk.DoubleVar(value=0)
        ttk.Progressbar(outer, variable=self.percent, maximum=100).pack(fill='x', pady=(12, 5))
        self.status = tk.StringVar(value='请选择一条字幕修改。生成视频需要等待进度到100%，仅保存文稿不会产生新视频。')
        ttk.Label(outer, textvariable=self.status, wraplength=1100).pack(anchor='w')
        self.path_label = tk.StringVar(value=f'编辑文稿：{document}')
        ttk.Label(outer, textvariable=self.path_label, wraplength=1100).pack(anchor='w', pady=(5, 0))
        self.loading = False
        self.refresh()
        if fonts:
            book.select(font_page)
        self.dirty = False
        root.after(150, self.poll)

    def open_external(self):
        if self.busy:
            return
        folder = Path(self.data.get('导入来源',self.path)).parent
        filename = self.filedialog.askopenfilename(parent=self.root, title='选择外部字幕JSON',
            initialdir=str(folder), filetypes=[('JSON字幕文件','*.json'),('所有文件','*.*')])
        if not filename:
            return
        try:
            candidate = import_document(Path(filename),self.data,self.config)
        except (OSError,ValueError,KeyError,TypeError) as error:
            self.messagebox.showerror('无法打开字幕JSON',str(error))
            return
        if self.dirty:
            answer = self.messagebox.askyesnocancel('保存当前修改','当前字幕有未保存的修改，导入前保存吗？')
            if answer is None or answer and not self.save():
                return
        self.loading = True
        self.selected = None  # Never commit the old row into the new document.
        self.data = candidate
        self.names = {name:document_names(self.data).get(name,name) for name in SLOTS}
        self.internal_names = {v:k for k,v in self.names.items()}
        self.filter_picker.configure(values=['全部',*self.names.values()])
        self.slot_picker.configure(values=list(self.names.values()))
        self.filter.set('全部')
        self.slot.set('')
        self.start.set('')
        self.end.set('')
        self.title.set('')
        self.text.delete('1.0','end')
        self.text.edit_reset()
        self.text.edit_modified(False)
        for label,var in self.fonts.items():
            var.set(str(normalized_sizes(self.data['字号'])[label]))
            self.font_labels[label].configure(text=self.names[label])
            for key,field in self.styles[label].items():
                base=self.config['layout'][SLOTS[label]]
                default=base.get(STYLE_FIELDS[key],self.config.get('font','KaiTi') if key=='字体' else self.config.get('scroll_speed',1) if key=='滚动倍速' else '')
                field.set(str(self.data.get('字幕样式',{}).get(stored_column(label,self.names),{}).get(key,default)))
        self.tree.column('slot',width=155 if self.data['栏目名称'] else 70)
        self.refresh()
        self.loading = False
        self.dirty = True
        self.percent.set(0)
        self.path_label.set(f'导入来源：{filename}\n保存到当前文稿：{self.path}')
        note = '外部源文件保持原样。' if Path(filename).resolve()!=self.path.resolve() else '这是当前编辑文稿。'
        self.status.set(f'已载入{len(self.data["字幕"])}条字幕。保存或生成时写入当前文稿，{note}')

    def changed(self):
        if not getattr(self, 'loading', True):
            self.dirty = True

    def text_changed(self, event):
        if self.text.edit_modified():
            self.changed()
            self.text.edit_modified(False)

    def commit_row(self):
        if self.selected is None:
            return
        self.data['字幕'][self.selected].update({'栏目': stored_column(self.internal_names.get(self.slot.get(),self.slot.get()),self.names), '开始秒': self.start.get(),
            '结束秒': self.end.get(), '标题': self.title.get(), '文字': self.text.get('1.0', 'end-1c'), '显示': self.visible.get()})
        self.data['字幕'][self.selected]['样式']={key:var.get().strip() for key,var in self.row_style.items() if var.get().strip()}

    def refresh(self, focus=None):
        self.commit_row()
        self.selected = None
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.data['字幕']):
            if self.filter.get() not in ('全部', self.names[column_key(row['栏目'])]):
                continue
            self.tree.insert('', 'end', iid=str(i), values=('是' if row.get('显示', True) else '隐藏', self.names[column_key(row['栏目'])],
                row['开始秒'], row['结束秒'], row['文字'].replace('\n', ' ')[:100]))
        rows = self.tree.get_children()
        target = str(focus) if focus is not None and str(focus) in rows else rows[0] if rows else None
        if target is not None:
            self.tree.selection_set(target)
            self.tree.see(target)
            self.select(None)

    def select(self, event):
        selection = self.tree.selection()
        if not selection or int(selection[0]) == self.selected:
            return
        previous = self.selected
        self.commit_row()
        if previous is not None and self.tree.exists(str(previous)):
            row = self.data['字幕'][previous]
            self.tree.item(str(previous), values=('是' if row['显示'] else '隐藏', self.names[column_key(row['栏目'])], row['开始秒'], row['结束秒'], row['文字'].replace('\n', ' ')[:100]))
        self.selected = int(selection[0])
        row = self.data['字幕'][self.selected]
        self.loading = True
        self.slot.set(self.names[column_key(row['栏目'])])
        self.start.set(str(row['开始秒']))
        self.end.set(str(row['结束秒']))
        self.title.set(row.get('标题', ''))
        self.visible.set(row.get('显示', True))
        for key,var in self.row_style.items():var.set(str(row.get('样式',{}).get(key,'')))
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', row['文字'])
        self.text.edit_modified(False)
        self.loading = False

    def add(self):
        self.commit_row()
        self.data['字幕'].append({'编号': 'edit-' + uuid.uuid4().hex[:12], '栏目': stored_column(self.internal_names.get(self.slot.get(),self.slot.get()) or '导聆',self.names),
                                 '开始秒': 27.5, '结束秒': 30.5, '标题': '', '文字': '', '显示': True})
        self.filter.set('全部')
        self.refresh(len(self.data['字幕']) - 1)
        self.dirty = True

    def save(self):
        self.commit_row()
        try:
            sizes = {k: int(v.get()) for k, v in self.fonts.items()}
            if any(not 12 <= v <= 120 for v in sizes.values()):
                raise ValueError()
        except ValueError:
            self.messagebox.showerror('字号未保存', '字号请输入12至120的整数。')
            return False
        self.data['字号'] = stored_sizes(sizes,self.names)
        try:
            settings={}
            for label,fields in self.styles.items():
                values={key:var.get().strip() for key,var in fields.items()}
                validate_style(values,{**self.config['layout'][SLOTS[label]],'font_size':sizes[label]},self.config)
                settings[stored_column(label,self.names)]=values
            self.data['字幕样式']=settings
            for row in self.data['字幕']:
                label=column_key(row['栏目'])
                base={**self.config['layout'][SLOTS[label]],'font_size':sizes[label]}
                base.update(validate_style(settings[stored_column(label,self.names)],base,self.config))
                validate_style(row.get('样式',{}),base,self.config)
        except ValueError as error:
            self.messagebox.showerror('样式未保存',str(error));return False
        try:
            write(self.path, self.data)
            # Preserve local font preferences for the existing Ravel projects.
            if self.package.resolve()==PACKAGE.resolve() or self.package.resolve()==full_paths()[0].resolve():
                write(configured_path('font_settings'), self.data['字号'])
        except OSError as error:
            self.messagebox.showerror('保存失败', str(error))
            return False
        self.dirty = False
        self.status.set('修改已保存。点击“保存并生成新视频”后才会产生新MP4。')
        self.refresh(self.selected)
        return True

    def generate(self, ass_only=False):
        if self.busy or not self.save():
            return
        try:
            prepare(self.data, self.package)
        except (ValueError, KeyError, OSError) as error:
            self.messagebox.showerror('请调整这一条字幕', str(error))
            return
        self.busy = True
        self.percent.set(0)
        for button in (self.render_button, self.ass_button, self.save_button, self.import_button):
            button.configure(state='disabled')
        snapshot = copy.deepcopy(self.data)
        def worker():
            try:
                path = export(snapshot, self.package, lambda p, m: self.messages.put(('progress', p, m)), ass_only)
                self.messages.put(('done', path, ass_only))
            except Exception as error:
                self.messages.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                item = self.messages.get_nowait()
                if item[0] == 'progress':
                    self.percent.set(item[1])
                    self.status.set(item[2])
                    continue
                self.busy = False
                for button in (self.render_button, self.ass_button, self.save_button, self.import_button):
                    button.configure(state='normal')
                if item[0] == 'error':
                    self.status.set('生成失败；旧视频和修改文稿均已保留。')
                    self.messagebox.showerror('生成失败', item[1])
                else:
                    path, ass_only = item[1:]
                    self.status.set(f'已生成：{path}')
                    if not ass_only:
                        self.result = path
                    self.messagebox.showinfo('字幕已导出' if ass_only else '新视频已生成', str(path))
        except queue.Empty:
            pass
        self.root.after(150, self.poll)

    def latest(self):
        if self.result:
            return self.result
        import json
        pointer = self.package / 'latest-caption-export.json'
        if pointer.exists():
            return Path(json.loads(pointer.read_text(encoding='utf-8'))['video'])
        old = self.package / 'latest-font-export.json'
        if old.exists():
            return self.package / json.loads(old.read_text(encoding='utf-8'))['video']
        return None

    def open_result(self):
        path = self.latest()
        if path and path.exists():
            os.startfile(path)
        else:
            self.messagebox.showinfo('还没有成片', '请先点击“保存并生成新视频”，等待进度到100%。')

    def open_folder(self):
        path = self.latest()
        os.startfile(path.parent if path else self.package)

    def close(self):
        if self.busy:
            self.messagebox.showinfo('视频正在生成', '请等待生成结束后再关闭，以免中断本次导出。')
            return
        if self.dirty:
            answer = self.messagebox.askyesnocancel('保存修改', '关闭前保存字幕修改吗？')
            if answer is None or answer and not self.save():
                return
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--document', type=Path)
    target=parser.add_mutually_exclusive_group()
    target.add_argument('--full',action='store_true',help='使用配置中的拉威尔左手钢协完整版（兼容参数）')
    target.add_argument('--project',help='选择配置中的项目ID，例如mother-goose、ravel-full、ravel-sample')
    target.add_argument('--panels',action='store_true',help='调整普二和声／配器面板的整体大小和声部颜色')
    parser.add_argument('--fonts', action='store_true')
    parser.add_argument('--render', action='store_true', help='直接按保存的文稿生成视频，不打开窗口')
    parser.add_argument('--ass-only', action='store_true')
    args = parser.parse_args()
    explicit_target=bool(args.project or args.full or args.package or args.document or args.panels)
    try:
        args.package,args.document=resolve_target(args)
    except ValueError as error:
        parser.error(str(error))
    if args.render or args.ass_only:
        try:
            if args.panels:
                if args.ass_only:raise ValueError('可视化面板不使用ASS；请生成样片')
                from backend.video_export.visual_panels import load_settings
                render_visual_sample(load_settings())
            else:export(load_document(args.document, args.package), args.package, ass_only=args.ass_only)
        except Exception as error:
            print(f'生成失败：{error}', file=sys.stderr)
            raise SystemExit(1)
    else:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        try:
            if not explicit_target:
                chosen=choose_project(root)
                if chosen is None:
                    root.destroy()
                    return
                if chosen=='panels':args.panels=True
                else:args.package,args.document=chosen
            root.deiconify()
            if args.panels:PanelEditor(root)
            else:Editor(root, args.package, args.document, args.fonts)
        except Exception as error:
            messagebox.showerror('字幕编辑器无法启动', str(error))
            root.destroy()
            raise SystemExit(1)
        root.mainloop()


if __name__ == '__main__':
    main()
