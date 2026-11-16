"""Read-only XLSX extraction, strict SKU matching, and final workbook checks.

Python standard library only. No browser, network, or workbook writes.
"""
import argparse
import json
import posixpath
import re
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET

X = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
NS = {'x': X}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def output(path, report):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def identifier(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+', value):
        raise ValueError(f'{field} must be a complete decimal string; got {value!r}')
    return value


def norm(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).casefold()


def attributes(record):
    raw = record.get('attributes')
    if not isinstance(raw, dict) or not raw:
        raise ValueError('attributes must be a nonempty object with string values')
    result = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str) or not norm(value):
            raise ValueError('attribute names and values must be nonempty strings')
        key = norm(key)
        if key in ('规格', '尺码', '鞋码'):
            key = '尺码'
        if key in result:
            raise ValueError(f'attribute aliases collide: {key}')
        result[key] = norm(value)
    return result


def link_matches(url, goods_id):
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    return (parsed.scheme in ('http', 'https') and bool(parsed.netloc)
            and parse_qs(parsed.query).get('id') == [goods_id])


def relation_part(owner, target):
    if target.startswith('/'):
        name = target.lstrip('/')
    else:
        name = posixpath.normpath(posixpath.join(posixpath.dirname(owner), target))
    if name.startswith('../'):
        raise ValueError('relationship escapes the package')
    return name


def read_xlsx(path, sheet_name=None):
    with zipfile.ZipFile(path) as z:
        workbook = ET.fromstring(z.read('xl/workbook.xml'))
        workbook_rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        relations = {r.get('Id'): r for r in workbook_rels}
        sheets = workbook.find(f'{{{X}}}sheets')
        names = [s.get('name') for s in sheets]
        if sheet_name is None:
            if len(names) != 1:
                raise ValueError(f'--sheet is required for multiple sheets: {names}')
            sheet_name = names[0]
        sheet = next((s for s in sheets if s.get('name') == sheet_name), None)
        if sheet is None:
            raise ValueError(f'sheet {sheet_name!r} does not exist: {names}')
        relation = relations[sheet.get(f'{{{R}}}id')]
        if relation.get('TargetMode') == 'External':
            raise ValueError('external worksheet is unsupported')
        part = relation_part('xl/workbook.xml', relation.get('Target'))
        root = ET.fromstring(z.read(part))
        shared = []
        shared_rel = next((r for r in workbook_rels if r.get('Type', '').endswith('/sharedStrings')), None)
        shared_part = relation_part('xl/workbook.xml', shared_rel.get('Target')) if shared_rel is not None else 'xl/sharedStrings.xml'
        if shared_part in z.namelist():
            shared = [''.join(t.text or '' for t in n.iter(f'{{{X}}}t'))
                      for n in ET.fromstring(z.read(shared_part))]
        rows, unsafe = [], []
        for row in root.findall('x:sheetData/x:row', NS):
            vals, types, formulas = {}, {}, {}
            for cell in row.findall('x:c', NS):
                ref = cell.get('r')
                col = re.fullmatch(r'([A-Z]+)[0-9]+', ref).group(1)
                kind = cell.get('t', 'n')
                v = cell.find('x:v', NS)
                value = v.text or '' if v is not None else ''
                if kind == 's':
                    value = shared[int(value)] if value else ''
                elif kind == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.iter(f'{{{X}}}t'))
                vals[col], types[col] = value, kind
                formula = cell.find('x:f', NS)
                if formula is not None:
                    formulas[col] = formula.text or ''
                if kind == 'n' and value and (len(re.sub(r'[^0-9]', '', value.lstrip('0'))) > 15 or 'e' in value.lower()):
                    unsafe.append(ref)
            rows.append({'row': int(row.get('r')), 'values': vals, 'types': types, 'formulas': formulas})
        links = {}
        rels_part = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
        sheet_rels = ET.fromstring(z.read(rels_part)) if rels_part in z.namelist() else []
        targets = {r.get('Id'): r.get('Target') for r in sheet_rels if r.get('Type', '').endswith('/hyperlink')}
        for link in root.findall('x:hyperlinks/x:hyperlink', NS):
            links[link.get('ref')] = targets.get(link.get(f'{{{R}}}id'), link.get('location', ''))
        return {'file': str(Path(path).resolve()), 'sheet': sheet_name, 'availableSheets': names,
                'rows': rows, 'unsafeNumericCells': unsafe, 'hyperlinks': links,
                'validationCount': len(root.findall('x:dataValidations/x:dataValidation', NS)),
                'commentParts': [n for n in z.namelist() if re.search(r'(^|/)comments[^/]*\.xml$', n, re.I)],
                'vmlParts': [n for n in z.namelist() if n.lower().endswith('.vml')]}


def match(requested, pdd_rows, douyin_rows):
    if not all(isinstance(rows, list) for rows in (requested, pdd_rows, douyin_rows)):
        raise ValueError('all three inputs must be JSON arrays')
    for goods_id in requested:
        identifier(goods_id, 'requested ID')
    if len(set(requested)) != len(requested) or not requested:
        raise ValueError('requested IDs must be nonempty and deduplicated in user order')
    pdd = defaultdict(list)
    for record in pdd_rows:
        pdd[identifier(record.get('pddGoodsId'), 'pddGoodsId')].append(record)
        identifier(record.get('pddSkuId'), 'pddSkuId')
    if set(pdd) - set(requested):
        raise ValueError('PDD input has IDs outside the requested list')
    dy = defaultdict(list)
    for record in douyin_rows:
        identifier(record.get('douyinGoodsId'), 'douyinGoodsId')
        identifier(record.get('douyinSkuId'), 'douyinSkuId')
        if not isinstance(record.get('model'), str) or not record['model'].strip():
            raise ValueError('Douyin model must be a nonempty string')
        dy[record['model']].append(record)
    verified, issues = [], []
    for goods_id in requested:
        def issue(reason, **extra):
            issues.append({'pddGoodsId': goods_id, 'reason': reason, **extra})
        if len(pdd[goods_id]) != 1:
            issue('pdd_selected_sku_missing_or_multiple', count=len(pdd[goods_id]))
            continue
        record = pdd[goods_id][0]
        model = record.get('model')
        if not isinstance(model, str) or not model.strip():
            issue('pdd_model_missing')
            continue
        candidates = dy.get(model, [])
        goods = {r['douyinGoodsId'] for r in candidates}
        if len(goods) != 1:
            issue('douyin_product_missing_or_ambiguous', model=model, candidateGoods=sorted(goods))
            continue
        code = record.get('pddSkuCode')
        if not isinstance(code, str) or not code.strip():
            issue('sku_code_missing_manual_verification_required')
            continue
        candidates = [r for r in candidates if r.get('douyinSkuCode') == code]
        if len(candidates) != 1:
            issue('douyin_sku_missing_or_ambiguous', model=model, skuCode=code, count=len(candidates))
            continue
        candidate = candidates[0]
        try:
            p_attrs, d_attrs = attributes(record), attributes(candidate)
        except ValueError as error:
            issue('attributes_invalid', detail=str(error))
            continue
        if p_attrs != d_attrs:
            issue('spec_mismatch', pddAttributes=p_attrs, douyinAttributes=d_attrs)
            continue
        if not link_matches(candidate.get('douyinUrl'), candidate['douyinGoodsId']):
            issue('link_goods_id_mismatch_or_missing', douyinGoodsId=candidate['douyinGoodsId'])
            continue
        verified.append({key: value for key, value in {
            'pddGoodsId': goods_id, 'pddSkuId': record['pddSkuId'],
            'douyinUrl': candidate['douyinUrl'], 'douyinSkuId': candidate['douyinSkuId'],
            'douyinGoodsId': candidate['douyinGoodsId'], 'model': model, 'platform': '抖音',
            'pddSkuCode': code, 'douyinSkuCode': candidate['douyinSkuCode'],
            'pddSpec': record.get('pddSpec', ''), 'douyinSpec': candidate.get('douyinSpec', ''),
            'pddAttributes': record['attributes'], 'douyinAttributes': candidate['attributes']
        }.items()})
    return {'requestedCount': len(requested), 'matchedCount': len(verified), 'verifiedRows': verified, 'issues': issues}


def verify_workbook(workbook, expected, columns, first_row, require_hyperlinks):
    if isinstance(expected, dict):
        if expected.get('issues'):
            raise ValueError('match report contains unresolved issues')
        expected = expected.get('verifiedRows')
    if not isinstance(expected, list) or not expected:
        raise ValueError('expected must be a nonempty array or successful match report')
    seen = set()
    for record in expected:
        for key in ('pddGoodsId', 'pddSkuId', 'douyinGoodsId', 'douyinSkuId'):
            identifier(record.get(key), key)
        if record['pddGoodsId'] in seen:
            raise ValueError('expected records contain duplicate PDD goods IDs')
        seen.add(record['pddGoodsId'])
        if not link_matches(record.get('douyinUrl'), record['douyinGoodsId']):
            raise ValueError('expected link has missing or mismatched goods ID')
    by_id = defaultdict(list)
    for row in workbook['rows']:
        if row['row'] >= first_row:
            by_id[row['values'].get(columns[0], '')].append(row)
    fields = ('pddGoodsId', 'pddSkuId', 'douyinUrl', 'douyinSkuId', 'platform')
    problems, verified = [], []
    for record in expected:
        goods_id = record['pddGoodsId']
        found = by_id.get(goods_id, [])
        if len(found) != 1:
            problems.append({'pddGoodsId': goods_id, 'reason': 'missing_or_duplicate', 'count': len(found)})
            continue
        row = found[0]
        count_before = len(problems)
        for col, key in zip(columns, fields):
            ref = f"{col}{row['row']}"
            if row['values'].get(col, '') != record.get(key, ''):
                problems.append({'cell': ref, 'reason': 'value_mismatch', 'field': key})
            if key in ('pddGoodsId', 'pddSkuId', 'douyinSkuId') and row['types'].get(col) not in ('s', 'inlineStr'):
                problems.append({'cell': ref, 'reason': 'id_not_stored_as_string'})
            if col in row['formulas']:
                problems.append({'cell': ref, 'reason': 'unexpected_formula_in_identifier_or_link'})
            if key == 'douyinUrl':
                link = workbook['hyperlinks'].get(ref)
                if (require_hyperlinks and not link) or (link and link != record['douyinUrl']):
                    problems.append({'cell': ref, 'reason': 'hyperlink_missing_or_target_mismatch'})
        if len(problems) == count_before:
            verified.append({'pddGoodsId': goods_id, 'row': row['row']})
    return {'file': workbook['file'], 'sheet': workbook['sheet'], 'expectedCount': len(expected),
            'verifiedCount': len(verified), 'verifiedRows': verified, 'issues': problems,
            'hyperlinkCount': len(workbook['hyperlinks']), 'validationCount': workbook['validationCount'],
            'commentParts': workbook['commentParts'], 'vmlParts': workbook['vmlParts']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    reader = sub.add_parser('read-xlsx')
    reader.add_argument('--input', required=True)
    reader.add_argument('--sheet')
    reader.add_argument('--out', required=True)
    matcher = sub.add_parser('match')
    for name in ('requested', 'pdd', 'douyin', 'out'):
        matcher.add_argument('--' + name, required=True)
    verifier = sub.add_parser('verify-xlsx')
    verifier.add_argument('--input', required=True)
    verifier.add_argument('--sheet')
    verifier.add_argument('--expected', required=True)
    verifier.add_argument('--columns', default='A,B,C,D,E')
    verifier.add_argument('--first-row', type=int, default=1)
    verifier.add_argument('--require-hyperlinks', action='store_true')
    verifier.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'read-xlsx':
            report = read_xlsx(args.input, args.sheet)
        elif args.command == 'match':
            report = match(read_json(args.requested), read_json(args.pdd), read_json(args.douyin))
        else:
            columns = [c.strip().upper() for c in args.columns.split(',')]
            if len(columns) != 5 or len(set(columns)) != 5 or any(not re.fullmatch(r'[A-Z]+', c) for c in columns):
                raise ValueError('--columns must contain five distinct Excel column names')
            report = verify_workbook(read_xlsx(args.input, args.sheet), read_json(args.expected), columns,
                                     args.first_row, args.require_hyperlinks)
        output(args.out, report)
        count = report.get('matchedCount', report.get('verifiedCount', len(report.get('rows', []))))
        print(json.dumps({'command': args.command, 'count': count, 'issues': len(report.get('issues', [])),
                          'out': str(Path(args.out).resolve())}, ensure_ascii=True))
        return 2 if report.get('issues') else 0
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile, ET.ParseError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
