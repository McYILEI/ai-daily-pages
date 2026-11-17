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
        })
    for body in re.findall(r'<details class="more">\s*<summary>(.*?)</summary>', h, re.S):
        nm = re.search(r'<span class="mo-name">(.*?)<span class="roles">', body, re.S)
        name = clean_name(nm.group(1) if nm else '')
        mt = text((re.search(r'<span class="mo-title">(.*?)</span>', body, re.S) or [None, ''])[1])
        line = mt.split('：', 1)[1] if '：' in mt[:30] else mt
        items.append({
            'anchor': '#:~:text=' + re.sub(r'[\s&,-]', lambda m: '%%%02X' % ord(m.group()), name),
            'no': '%02d' % (len(items) + 1), 'name': name, 'keywords': '', 'tag': '', 'color': 'yellow',
            'line': clip(line, 36), 'roles': roles_in(body),
        })
    for i, it in enumerate(items):
        it['no'] = it['no'] or '%02d' % (i + 1)
        it['roles'] = it['roles'] or ['product']
    mp = os.path.join(ROOT, 'hub-meta', date + '.json')
    if os.path.isfile(mp):
        with open(mp, encoding='utf-8') as fh:
            meta = json.load(fh).get('items', {})
        for it in items:
            m = next((v for k, v in meta.items() if k and k in it['name']), None)
            if m:
                for k_src, k_dst in (('keywords', 'keywords'), ('tag', 'tag'), ('tag_color', 'color'), ('line', 'line')):
                    if m.get(k_src) and not (k_dst in ('keywords', 'tag', 'line') and it[k_dst] and it['anchor'].startswith('#s')):
                        it[k_dst] = m[k_src]
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
    return '<span class="roles"><span class="roles-l">推荐给</span>%s</span>' % ''.join(
        '<span class="role r-%s">%s</span>' % (k, ROLE_NAME[k]) for k in roles)


def build():
    issues = scan()
    if not issues:
        sys.exit('没有找到任何新版早报页面')
    counts = {k: 0 for k, _ in ROLES}
    nav, sections = [], []
    for iss in issues:
        date, href = iss['date'], './%s/' % iss['slug']
        label = '%s %s · 第 %02d 期' % (short_date(date), weekday(date), iss['no'])
        rows = []
        for it in iss['items']:
            for r in it['roles']:
                counts[r] += 1
            kw = '<span class="ol-kw">%s</span>' % esc(it['keywords']) if it['keywords'] else ''
            tag = '<span class="tag t-%s">%s</span>' % (esc(it['color']), esc(it['tag'])) if it['tag'] else ''
            rows.append('<li data-roles="%s"><a href="%s%s"><span class="no">%s</span><span class="ol-main">'
                        '<span class="ol-name">%s</span>%s<span class="ol-line">%s%s</span></span>%s</a></li>'
                        % (' '.join(it['roles']), href, esc(it['anchor']), esc(it['no']), esc(it['name']), kw,
                           tag, esc(it['line']), roles_html(it['roles'])))
        nav.append('<li><a href="#issue=%s" data-issue="%s"><span class="ni-no">第 %02d 期</span>'
                   '<span class="ni-date">%s %s</span></a></li>' % (date, date, iss['no'], short_date(date), weekday(date)))
        sections.append(
            '<section class="issue-sec" id="issue-%s" data-issue="%s">\n'
            '<div class="sec-h"><div class="issue sm">%s</div><a class="open" href="%s">查看全文 →</a></div>\n'
            '<div class="note"><div class="label">本期导读</div><p>%s</p></div>\n'
            '<ol class="outline">\n%s\n</ol>\n</section>'
            % (date, date, esc(label), href, esc(iss['note']), '\n'.join(rows)))
    latest = issues[0]
    total = sum(len(i['items']) for i in issues)
    role_nav = '<li><button class="rb" data-role="" aria-pressed="true">全部岗位<span class="c">%d</span></button></li>' % total
    role_nav += ''.join('<li><button class="rb" data-role="%s" aria-pressed="false"><span class="role r-%s">%s</span><span class="c">%d</span></button></li>'
                        % (k, k, n, counts[k]) for k, n in ROLES)
    with open(os.path.join(ROOT, 'hub_template.html'), encoding='utf-8') as f:
        tpl = f.read()
    rep = {
        '{{LATEST_LABEL}}': esc('最新 · %s %s · 第 %02d 期' % (short_date(latest['date']), weekday(latest['date']), latest['no'])),
        '{{LATEST_HREF}}': './%s/' % latest['slug'],
        '{{ISSUE_COUNT}}': str(len(issues)), '{{ITEM_COUNT}}': str(total),
        '{{NAV_ISSUES}}': '\n'.join(nav), '{{NAV_ROLES}}': role_nav, '{{SECTIONS}}': '\n'.join(sections),
    }
    for k, v in rep.items():
        tpl = tpl.replace(k, v)
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(tpl)
    print('index.html 已生成：%d 期，%d 条' % (len(issues), total))


if __name__ == '__main__':
    build()
