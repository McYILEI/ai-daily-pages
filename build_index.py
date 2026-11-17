#!/usr/bin/env python3
"""有智青年 AI市集 · AI市集早报 —— 总入口（根目录 index.html）生成脚本。

用法：在仓库根目录运行  python3 build_index.py  ，然后提交 index.html。

它扫描根目录下每个早报文件夹（<slug>/index.html，新版早报页面），直接从页面里读出
期号、日期、本期导读、正文条目（名称、推荐岗位、标签、关键词、一句话），生成可以按
时间、按岗位（产品 / 开发 / 运营）浏览的总入口。早报页面本身不会被修改。

- 日期：优先用根目录的标记文件 .slug-YYYY-MM-DD（内容是文件夹名），否则用页面标题里的 MM/DD。
- 可选 hub-meta/<YYYY-MM-DD>.json：给条目补充总入口展示用的关键词/标签/一句话
  （按条目名称包含匹配）。没有的条目会自动用页面里的内容。
"""
import datetime, html, json, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WEEK = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
ROLES = [('product', '产品'), ('dev', '开发'), ('ops', '运营')]
ROLE_NAME = dict(ROLES)
ROLE_BY_CN = {v: k for k, v in ROLES}
# 总入口按话题分类（不按岗位）。卡片上只显示一个主话题，按这个优先级取；筛选时条目有的话题都算。
TOPICS = [('travel', 'AI 出行'), ('agent', 'AI 助理'), ('harness', 'AI 工程'), ('content', 'AI 内容')]
TOPIC_NAME = dict(TOPICS)
TOPIC_PRIORITY = ['content', 'travel', 'harness', 'agent']
ISSUES_DIR = os.environ.get('ISSUES_DIR', '/workspace/ai-innovation-reports/issues')
EMOJI = re.compile('[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D\u2B00-\u2BFF]+')


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def text(s):
    s = re.sub(r'<br\s*/?>', '', s or '')
    return html.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def clean_name(s):
    return EMOJI.sub('', text(s)).strip()


def clip(s, n):
    return s if len(s) <= n else s[:n - 1].rstrip('，、；：,; ') + '…'


def roles_in(fragment):
    found = [ROLE_BY_CN.get(text(r)) for r in re.findall(r'<span class="role r-\w+">(.*?)</span>', fragment)]
    return [r for r in found if r]


def cover_of(body):
    """条目的配图（页面里内嵌的图片）或者要点数字（gist），给卡片封面用。"""
    out = {}
    img = re.search(r'<img src="(data:image/(\w+);base64,([^"]+))" alt="([^"]*)"', body)
    if img:
        out['img_b64'], out['img_alt'] = img.group(3), text(img.group(4))
    else:
        url = re.search(r'<img src="((?:https?:)?[^"]+)" alt="([^"]*)"', body)
        if url:
            out['img_url'], out['img_alt'] = url.group(1), text(url.group(2))
    g = re.search(r'<div class="gist-stat">(.*?)</div>\s*<div class="gist-line">(.*?)</div>', body, re.S)
    if g:
        out['cover_stat'], out['cover_line'] = text(g.group(1)), text(g.group(2))
    return out


def save_cover(date, no, b64):
    """把内嵌图片存成 assets/covers/<日期>-<编号>.jpg（宽 720）。"""
    import base64, io
    rel = 'assets/covers/%s-%s.jpg' % (date, no)
    path = os.path.join(ROOT, rel)
    if True:  # 每次重新生成，保证和早报页里的图一致
        os.makedirs(os.path.dirname(path), exist_ok=True)
        raw = base64.b64decode(b64)
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(raw)).convert('RGB')
            im.thumbnail((720, 720))
            im.save(path, 'JPEG', quality=84, optimize=True)
        except ImportError:
            rel = rel[:-4] + '.img'
            with open(os.path.join(ROOT, rel), 'wb') as f:
                f.write(raw)
    return './' + rel


def slug_dates():
    out = {}
    for f in os.listdir(ROOT):
        m = re.fullmatch(r'\.slug-(\d{4}-\d{2}-\d{2})', f)
        if m:
            with open(os.path.join(ROOT, f), encoding='utf-8') as fh:
                out[fh.read().strip()] = m.group(1)
    return out


def parse_issue(slug, h, date_hint):
    title = text((re.search(r'<title>(.*?)</title>', h, re.S) or [None, ''])[1])
    label = text((re.search(r'<div class="issue">(.*?)</div>', h, re.S) or [None, ''])[1])
    md = re.search(r'(\d{1,2})/(\d{1,2})', label or title)
    no = re.search(r'第\s*0*(\d+)\s*期', label or title)
    date = date_hint
    if not date and md:
        date = '%d-%02d-%02d' % (datetime.date.today().year, int(md.group(1)), int(md.group(2)))
    if not date:
        return None
    note = re.search(r'<div class="note">.*?<p>(.*?)</p>', h, re.S)
    # outline rows（本期提纲）keyed by anchor
    outline = {}
    for a, body in re.findall(r'<li><a href="#([\w-]+)">(.*?)</a></li>', h, re.S):
        g = lambda c: re.search(r'<span class="%s">(.*?)</span>' % c, body, re.S)
        tag = re.search(r'<span class="tag t-(\w+)">(.*?)</span>(.*?)</span>', body, re.S)
        outline[a] = {
            'name': clean_name(g('ol-name').group(1)) if g('ol-name') else '',
            'keywords': text(g('ol-kw').group(1)) if g('ol-kw') else '',
            'color': tag.group(1) if tag else 'lime',
            'tag': text(tag.group(2)) if tag else '',
            'line': text(tag.group(3)) if tag else '',
            'roles': roles_in(body),
        }
    h = h.split('<footer class="end"')[0]
    items = []
    for sid, body in re.findall(r'<article class="story" id="([\w-]+)">(.*?)</article>', h, re.S):
        o = outline.get(sid, {})
        head = (re.search(r'<header class="st-head">(.*?)</header>', body, re.S) or [None, ''])[1]
        tag = re.search(r'<span class="tag t-(\w+)">(.*?)</span>', head)
        st_title = text((re.search(r'<p class="st-title">(.*?)</p>', body, re.S) or [None, ''])[1])
        items.append({
            'anchor': '#' + sid,
            'no': text((re.search(r'<span class="st-no">(.*?)</span>', head) or [None, ''])[1]),
            'name': o.get('name') or clean_name((re.search(r'<h3 class="st-name">(.*?)</h3>', body, re.S) or [None, ''])[1]),
            'keywords': o.get('keywords', ''),
            'tag': o.get('tag') or (text(tag.group(2)) if tag else ''),
            'color': o.get('color') or (tag.group(1) if tag else 'lime'),
            'line': o.get('line') or clip(st_title, 36),
            'roles': roles_in(head) or o.get('roles') or [],
            'title': st_title,
            **cover_of(body),
        })
    for summ, mbody in re.findall(r'<details class="more">\s*<summary>(.*?)</summary>(.*?)</details>', h, re.S):
        body = summ
        nm = re.search(r'<span class="mo-name">(.*?)<span class="roles">', body, re.S)
        name = clean_name(nm.group(1) if nm else '')
        mt = text((re.search(r'<span class="mo-title">(.*?)</span>', body, re.S) or [None, ''])[1])
        line = mt.split('：', 1)[1] if '：' in mt[:30] else mt
        items.append({
            'anchor': '#:~:text=' + re.sub(r'[\s&,-]', lambda m: '%%%02X' % ord(m.group()), name),
            'no': '%02d' % (len(items) + 1), 'name': name, 'keywords': '', 'tag': '', 'color': 'yellow',
            'line': clip(line, 36), 'roles': roles_in(body), 'title': mt,
            **cover_of(mbody),
        })
    for i, it in enumerate(items):
        it['no'] = it['no'] or '%02d' % (i + 1)
        it['roles'] = it['roles'] or ['product']
    meta = {}
    mp = os.path.join(ROOT, 'hub-meta', date + '.json')
    if os.path.isfile(mp):
        with open(mp, encoding='utf-8') as fh:
            meta = json.load(fh).get('items', {})
        for it in items:
            m = next((v for k, v in meta.items() if k and k in it['name']), None)
            if m:
                for k in ('cover_stat', 'cover_line'):
                    if m.get(k) and not it.get(k):
                        it[k] = m[k]
                for k_src, k_dst in (('keywords', 'keywords'), ('tag', 'tag'), ('tag_color', 'color'), ('line', 'line')):
                    if m.get(k_src) and not (k_dst in ('keywords', 'tag', 'line') and it[k_dst] and it['anchor'].startswith('#s')):
                        it[k_dst] = m[k_src]
    # 话题：hub-meta 里的 topics 优先，其次是 issues/<日期>.json 里同名条目的 topics
    src = {}
    jp = os.path.join(ISSUES_DIR, date + '.json')
    if os.path.isfile(jp):
        with open(jp, encoding='utf-8') as fh:
            for x in json.load(fh).get('items', []):
                if x.get('name'):
                    src[x['name']] = x.get('topics') or []
    for k, v in meta.items():
        if v.get('topics'):
            src[k] = v['topics']
    for it in items:
        t = next((v for k, v in src.items() if k and k in it['name']), None) or []
        t = [x for x in t if x in TOPIC_NAME] or ['agent']
        it['topics'] = t
        it['topic'] = next(x for x in TOPIC_PRIORITY if x in t)
    return {'slug': slug, 'date': date, 'no': int(no.group(1)) if no else None,
            'note': text(note.group(1)) if note else '', 'items': items}


def scan():
    hints = slug_dates()
    issues = []
    for name in sorted(os.listdir(ROOT)):
        page = os.path.join(ROOT, name, 'index.html')
        if name.startswith('.') or not os.path.isfile(page):
            continue
        with open(page, encoding='utf-8') as f:
            h = f.read()
        if 'class="story"' not in h:          # 只收新版早报页面
            print('跳过（不是新版早报页面）：', name)
            continue
        iss = parse_issue(name, h, hints.get(name))
        if iss:
            issues.append(iss)
    issues.sort(key=lambda x: x['date'])
    for i, iss in enumerate(issues):
        iss['no'] = iss['no'] or i + 1
    return list(reversed(issues))


def weekday(date):
    y, m, d = map(int, date.split('-'))
    return WEEK[datetime.date(y, m, d).weekday()]


def short_date(date):
    _, m, d = date.split('-')
    return '%d/%d' % (int(m), int(d))


def roles_html(roles):
    return '<span class="roles">%s</span>' % ''.join(
        '<span class="role r-%s">%s</span>' % (k, ROLE_NAME[k]) for k in roles)


def cover_html(it, date):
    if it.get('img_b64'):
        src = save_cover(date, it['no'], it['img_b64'])
        return '<div class="cover img"><img src="%s" alt="%s" loading="lazy"></div>' % (esc(src), esc(it.get('img_alt', '')))
    if it.get('img_url'):
        return '<div class="cover img"><img src="%s" alt="%s" loading="lazy"></div>' % (esc(it['img_url']), esc(it.get('img_alt', '')))
    stat = it.get('cover_stat') or it.get('tag') or it['name']
    line = it.get('cover_line') or it.get('keywords') or ''
    return ('<div class="cover type"><span class="cv-no">%s</span><span class="cv-stat">%s</span>'
            '<span class="cv-line">%s</span></div>' % (esc(it['no']), esc(stat), esc(line)))


def build():
    issues = scan()
    if not issues:
        sys.exit('没有找到任何新版早报页面')
    counts = {k: 0 for k, _ in TOPICS}
    cards, options, past = [], [], []
    for iss in issues:
        date, href = iss['date'], './%s/' % iss['slug']
        wd = weekday(date)
        label = '第 %02d 期 · %s %s' % (iss['no'], short_date(date), wd)
        options.append('<option value="%s">%s</option>' % (date, esc(label)))
        past.append('<a class="past" href="%s"><span class="issue sm">%s %s · 第 %02d 期</span>'
                    '<span class="past-n">%d 条</span><span class="past-note">%s</span><span class="past-go">查看全文 →</span></a>'
                    % (href, short_date(date), wd, iss['no'], len(iss['items']), esc(clip(iss['note'], 70))))
        for it in iss['items']:
            for t in it['topics']:
                counts[t] += 1
            search = ' '.join([it['name'], it['keywords'], it['tag'], it['line'], it.get('title', ''),
                               it.get('cover_stat', ''), it.get('cover_line', '')]).lower()
            tag = '<span class="tag">%s</span>' % esc(it['tag']) if it['tag'] else ''
            chip = '<span class="topic tp-%s">%s</span>' % (it['topic'], TOPIC_NAME[it['topic']])
            kw = '<p class="kw">%s</p>' % esc(it['keywords']) if it['keywords'] else ''
            cards.append(
                '<article class="card" data-issue="%s" data-topics="%s" data-search="%s">\n'
                '<a class="card-link" href="%s%s" aria-label="打开：%s">%s</a>\n'
                '<div class="card-body"><div class="card-tags">%s%s</div>'
                '<h3>%s</h3>%s<p class="sum">%s</p></div>\n'
                '<footer><span class="meta">第 %02d 期 · %s %s</span><a class="go" href="%s%s">打开 →</a></footer>\n</article>'
                % (date, ' '.join(it['topics']), esc(search + ' ' + ' '.join(TOPIC_NAME[t].lower() for t in it['topics'])),
                   href, esc(it['anchor']), esc(it['name']),
                   cover_html(it, date), chip, tag, esc(it['name']), kw,
                   esc(it['line']), iss['no'], short_date(date), wd, href, esc(it['anchor'])))
    latest = issues[0]
    total = len(cards)
    tabs = '<button class="pill" data-topic="" aria-pressed="true"><span class="pl">全部</span><span class="c">%d</span></button>' % total
    tabs += ''.join('<button class="pill" data-topic="%s" aria-pressed="false"><span class="dot tp-%s"></span><span class="pl">%s</span><span class="c">%d</span></button>'
                    % (k, k, n, counts[k]) for k, n in TOPICS)
    with open(os.path.join(ROOT, 'hub_template.html'), encoding='utf-8') as f:
        tpl = f.read()
    rep = {
        '{{LATEST_LABEL}}': esc('最新 · %s %s · 第 %02d 期' % (short_date(latest['date']), weekday(latest['date']), latest['no'])),
        '{{LATEST_HREF}}': './%s/' % latest['slug'],
        '{{ISSUE_COUNT}}': str(len(issues)), '{{ITEM_COUNT}}': str(total),
        '{{TOPIC_TABS}}': tabs, '{{ISSUE_OPTIONS}}': '\n'.join(options),
        '{{CARDS}}': '\n'.join(cards), '{{PAST}}': '\n'.join(past),
    }
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(tpl)
    print('index.html 已生成：%d 期，%d 条' % (len(issues), total))


if __name__ == '__main__':
    build()
