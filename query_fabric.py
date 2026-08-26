
import sys
import json
import os
import re

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

REFERENCE_FILE = 'fabric_reference.json'

def load_json(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def get_category_by_model(model):
    if not model:
        return None
    first_char = str(model)[0]
    category_map = {
        '1': '上衣',
        '4': '大衣',
        '6': '裤子',
        '5': '马甲'
    }
    return category_map.get(first_char)

def get_table_by_category(category):
    table_map = {
        '上衣': ['TF上衣', '原算料表', '全里三件套', '无里三件套', '猎装'],
        '大衣': ['大衣', '猎装'],
        '裤子': ['TF西裤', '原算料表', '短裤'],
        '马甲': ['原算料表', '全里三件套', '无里三件套']
    }
    return table_map.get(category, [])

def query_pattern_rules(model):
    ref_data = load_json(REFERENCE_FILE)
    if ref_data and 'pattern_rules' in ref_data:
        pattern_dict = ref_data['pattern_rules']
        model_lower = model.lower()
        for pattern_code, rules in pattern_dict.items():
            if pattern_code.lower() == model_lower:
                return {'pattern_code': pattern_code, 'rules': rules}
        for pattern_code, rules in pattern_dict.items():
            if model_lower in pattern_code.lower():
                return {'pattern_code': pattern_code, 'rules': rules}
    return None

def match_trousers_by_rules(model, rules, size=None, width=None):
    ref_data = load_json(REFERENCE_FILE)
    results = []
    if not ref_data or 'tables' not in ref_data:
        return results
    rule_text = ' '.join(str(v) for v in rules.values() if v)
    is_shorts = '短裤' in rule_text or (rules.get('规则2') and '短' in str(rules.get('规则2')))
    if is_shorts:
        table_names = ['短裤']
    elif str(model).upper().startswith('6TF'):
        table_names = ['TF西裤', '原算料表']
    else:
        table_names = ['原算料表', 'TF西裤']
    exact_matches = []
    fallback_matches = []
    for table_name in table_names:
        if table_name not in ref_data['tables']:
            continue
        for row in ref_data['tables'][table_name].get('rows', []):
            name = str(row.get('版型', row.get('男装/素色或条纹', '')))
            if not name:
                continue
            if size is not None and str(size) not in row:
                continue
            if width is not None:
                w_val = row.get('门幅')
                if w_val is not None and abs(float(w_val) - float(width)) > 0.1:
                    continue
            if table_name == '原算料表':
                if '西裤' not in name and '裤长' not in name and '裤子' not in name:
                    continue
                if '无褶' in rule_text or '正常' in rule_text:
                    if '单褶' in name or '双褶' in name:
                        continue
                elif '单褶' in rule_text and '单褶' not in name:
                    continue
                elif '双褶' in rule_text and '双褶' not in name:
                    continue
            result = {'source': f'参考表-{table_name}', 'data': row}
            if str(model).upper() in name.upper():
                exact_matches.append(result)
            else:
                fallback_matches.append(result)
    # TF系列同版型可能有多个门幅；未指定门幅时默认优先门幅74。
    if str(model).upper().startswith('6TF') and width is None:
        def tf_width_priority(result):
            w = result['data'].get('门幅')
            try:
                return 0 if abs(float(w) - 74) < 0.1 else 1
            except (TypeError, ValueError):
                return 1
        exact_matches.sort(key=tf_width_priority)
        fallback_matches.sort(key=tf_width_priority)
    results.extend(exact_matches)
    results.extend(fallback_matches)
    return results

def query_fabric_calculation_by_rules(model, rules, size=None, width=None):
    ref_data = load_json(REFERENCE_FILE)
    results = []
    if not rules or not ref_data or 'tables' not in ref_data:
        return results
    category = get_category_by_model(model)
    if not category:
        return results
    if category == '裤子':
        return match_trousers_by_rules(model, rules, size, width)
    relevant_tables = get_table_by_category(category)
    rule3 = str(rules.get('规则3', ''))
    rule4 = str(rules.get('规则4', ''))
    has_double_row = '双排' in rule3
    # 大衣/猎装表按版型编码逐行标注，优先做版型精确匹配。
    model_upper = str(model).upper()
    for table_name in relevant_tables:
        if table_name not in ref_data['tables']:
            continue
        for row in ref_data['tables'][table_name].get('rows', []):
            row_model = str(row.get('版型', '')).upper()
            if row_model and row_model == model_upper:
                if size and str(size) not in row:
                    continue
                if width is not None:
                    w_val = row.get('门幅')
                    if w_val is not None and abs(float(w_val) - float(width)) > 0.1:
                        continue
                return [{'source': f'参考表-{table_name}', 'data': row}]
    for table_name in relevant_tables:
        if table_name not in ref_data['tables']:
            continue
        for row in ref_data['tables'][table_name].get('rows', []):
            key = row.get('男装/素色或条纹', row.get('版型', ''))
            if not key:
                continue
            # 带版型编码的行（大衣/猎装表）只走上面的精确匹配，避免串行取错。
            if re.fullmatch(r'\d[A-Z]{2,}\d+', str(row.get('版型', '')).upper()):
                continue
            if has_double_row:
                if '双排' not in str(key):
                    continue
            else:
                if '双排' in str(key):
                    continue
            if '全里' in rule4 and '全里' not in str(key):
                continue
            if '半里' in rule4 and '半里' not in str(key):
                continue
            if '无里' in rule4 and '无里' not in str(key):
                continue
            if size and str(size) not in row:
                continue
            if width is not None:
                w_val = row.get('门幅')
                if w_val is not None and abs(float(w_val) - float(width)) > 0.1:
                    continue
            results.append({'source': f'参考表-{table_name}', 'data': row})
    # 上衣默认按单西优先，避免只按“单排/全里”时误先匹配到套装行。
    if category == '上衣':
        results.sort(key=lambda r: (
            0 if '单西' in str(r['data'].get('男装/素色或条纹', r['data'].get('版型', ''))) else 1,
            1 if '套装' in str(r['data'].get('男装/素色或条纹', r['data'].get('版型', ''))) else 0,
        ))
    return results

def query_fabric_calculation(model, size=None, width=None):
    ref_data = load_json(REFERENCE_FILE)
    results = []
    if ref_data and 'tables' in ref_data:
        category = get_category_by_model(model)
        relevant_tables = get_table_by_category(category) if category else ref_data['tables'].keys()
        for table_name in relevant_tables:
            if table_name not in ref_data['tables']:
                continue
            for row in ref_data['tables'][table_name].get('rows', []):
                if size and str(size) not in row:
                    continue
                if width is not None:
                    w_val = row.get('门幅')
                    if w_val is not None and abs(float(w_val) - float(width)) > 0.1:
                        continue
                if model.lower() in str(row).lower():
                    results.append({'source': f'参考表-{table_name}', 'data': row})
    return results

def smart_query(model, size=None, width=None):
    results = []
    category = get_category_by_model(model)
    print(f"=== 面料计算查询: {model} {' ' + size if size else ''}{' 门幅' + str(width) if width else ''} ===")
    print(f"版型类别: {category if category else '未知'}")
    pattern_info = query_pattern_rules(model)
    if pattern_info:
        print("\n【1】版型档案匹配")
        print(f"  版型编码: {pattern_info['pattern_code']}")
        rules = pattern_info['rules']
        for k, v in rules.items():
            if v:
                print(f"  {k}: {v}")
        calc_by_rules = query_fabric_calculation_by_rules(model, rules, size, width)
        if calc_by_rules:
            print(f"\n【2】面料计算匹配（{category} - 根据版型规则）")
            for idx, result in enumerate(calc_by_rules[:6]):
                print(f"\n  {idx + 1}. {result['source']}")
                data = result['data']
                print(f"    版型: {data.get('版型', data.get('男装/素色或条纹', ''))}")
                if '门幅' in data:
                    print(f"    门幅: {data['门幅']}")
                if size and str(size) in data:
                    print(f"    {size}码耗量: {data[str(size)]} cm")
            results.extend(calc_by_rules)
    else:
        calc_direct = query_fabric_calculation(model, size, width)
        if calc_direct:
            print(f"\n【2】面料计算匹配（{category} - 直接查询）")
            for idx, result in enumerate(calc_direct[:6]):
                print(f"\n  {idx + 1}. {result['source']}")
                data = result['data']
                print(f"    版型: {data.get('版型', data.get('男装/素色或条纹', ''))}")
                if '门幅' in data:
                    print(f"    门幅: {data['门幅']}")
                if size and str(size) in data:
                    print(f"    {size}码耗量: {data[str(size)]} cm")
            results.extend(calc_direct)
    if not results:
        print("\n未找到面料计算参考数据")
    return results

def smart_query_json(model, size=None, width=None, length_adj=None, waist_adj=None, is_plaid=False, suit_type=None):
    result = {
        'ok': False,
        'message': '',
        'model': model,
        'size': size,
        'width': width,
        'category': None,
        'pattern_rules': {},
        'base_consumption': None,
        'width_adjustment': 0,
        'length_adjustment': 0,
        'waist_adjustment': 0,
        'plaid_adjustment': 0,
        'suit_adjustment': 0,
        'suit_type': suit_type,
        'breakdown': [],
        'total_consumption': None,
        'matched_item': None,
        'matched_source': None,
        'notes': []
    }
    category = get_category_by_model(model)
    result['category'] = category
    pattern_info = query_pattern_rules(model)
    if pattern_info:
        result['pattern_rules'] = pattern_info.get('rules', {})
    calc_results = []
    if pattern_info:
        calc_results = query_fabric_calculation_by_rules(model, pattern_info['rules'], size, width)
    else:
        calc_results = query_fabric_calculation(model, size, width)
    if not calc_results:
        result['message'] = '该版型未收录到算料表中，请核对版号'
        return json.dumps(result, ensure_ascii=False, indent=2)
    base_consumption = None
    matched_item = None
    matched_source = None
    for r in calc_results:
        if size and str(size) in r['data']:
            base_consumption = float(r['data'][str(size)])
            matched_item = r['data']
            matched_source = r['source']
            break
        elif '版型' in r['data'] and not size:
            matched_item = r['data']
            matched_source = r['source']
            break
    if base_consumption is None and matched_item and size:
        for k, v in matched_item.items():
            if str(k).isdigit() and isinstance(v, (int, float)):
                base_consumption = float(v)
                result['notes'].append(f"参考表中无{size}码数据，使用{str(k)}码数据代替")
                break
    if base_consumption is None:
        result['message'] = '未找到匹配的耗量数据'
        return json.dumps(result, ensure_ascii=False, indent=2)
    # 原算料表未标注门幅字段的最终匹配项，默认是门幅74。
    # 用户指定非74门幅时，只有最终匹配项本身有明确门幅，或已知固定系数（60/50）才继续计算；
    # 其他门幅（如65）不能自行估算，直接提示没有准确耗量。
    if width is not None:
        try:
            width_value = float(width)
        except (TypeError, ValueError):
            width_value = None
        if width_value is not None and abs(width_value - 74) > 0.1 and not any(abs(width_value - x) < 0.1 for x in (60, 50)):
            matched_width = None
            try:
                if matched_item and matched_item.get('门幅') is not None:
                    matched_width = float(matched_item.get('门幅'))
            except (TypeError, ValueError):
                matched_width = None
            if matched_width is None or abs(matched_width - width_value) > 0.1:
                result['message'] = f'参考表没有门幅{width_value:g}的准确耗量'
                result['matched_item'] = matched_item
                result['matched_source'] = matched_source
                return json.dumps(result, ensure_ascii=False, indent=2)
    result['ok'] = True
    result['base_consumption'] = round(base_consumption, 1)
    result['matched_item'] = matched_item
    result['matched_source'] = matched_source
    total = base_consumption
    breakdown_list = []
    breakdown_list.append({'name': '基础耗量', 'value': round(base_consumption, 1), 'description': '参考表基准耗量'})
    width_factor = 1.0
    width_desc = ''
    if width:
        if abs(width - 60) < 0.1:
            width_factor = 1.15
            width_desc = '门幅60，增加15%'
        elif abs(width - 50) < 0.1:
            width_factor = 1.3225
            width_desc = '门幅50，增加32.25%'
    if width_factor != 1.0:
        width_adj = base_consumption * (width_factor - 1)
        total = base_consumption * width_factor
        result['width_adjustment'] = round(width_adj, 1)
        breakdown_list.append({'name': '门幅调整', 'value': round(width_adj, 1), 'description': width_desc})
    # KK 系列西裤在 KN 耗量表基础上 +5cm（业务规则）。放在门幅调整之后，避免被门幅重赋 total 覆盖。
    if str(model).upper().startswith('6KK') and category == '裤子':
        kk_adj = 5
        total += kk_adj
        result['kk_adjustment'] = kk_adj
        breakdown_list.append({
            'name': 'KK系列加量',
            'value': kk_adj,
            'description': 'KK系列西裤在KN耗量表基础上+5cm'
        })
        result['notes'].append('KK系列西裤默认在KN耗量表基础上+5cm')
    if length_adj:
        adj = length_adj * 2
        total += adj
        length_adj_name = '裤长调整' if category == '裤子' else '衣长调整'
        result['length_adjustment'] = round(adj, 1)
        breakdown_list.append({'name': length_adj_name, 'value': round(adj, 1), 'description': ('裤长' if category == '裤子' else '衣长') + '+' + str(length_adj) + 'cm，耗量增加' + str(round(adj, 1)) + 'cm'})
    if waist_adj:
        total += waist_adj
        result['waist_adjustment'] = round(waist_adj, 1)
        breakdown_list.append({'name': '腰围调整', 'value': round(waist_adj, 1), 'description': '腰围+' + str(waist_adj) + 'cm'})
    if is_plaid:
        total += 10
        result['plaid_adjustment'] = 10
        breakdown_list.append({'name': '格子加量', 'value': 10, 'description': '格子面料增加10cm'})
    suit_adj = 0
    if suit_type:
        suit_text = str(suit_type).strip()
        if suit_text in ('2', '两件套', '套装'):
            suit_adj = -20
            suit_type = '两件套'
        elif suit_text in ('3', '三件套'):
            suit_adj = -30
            suit_type = '三件套'
        if suit_adj:
            total += suit_adj
            result['suit_adjustment'] = suit_adj
            result['suit_type'] = suit_type
            breakdown_list.append({'name': '套装调整', 'value': suit_adj, 'description': f'{suit_type}单件基础上减{abs(suit_adj)}cm'})
    result['breakdown'] = breakdown_list
    result['total_consumption'] = round(total, 1)
    result['message'] = '查询成功'
    return json.dumps(result, ensure_ascii=False, indent=2)

def query_rules():
    ref_data = load_json(REFERENCE_FILE)
    if ref_data and 'rules' in ref_data:
        return ref_data['rules']
    return None

def print_rules():
    rules = query_rules()
    if not rules:
        print('未找到业务规则')
        return
    print('=== 业务规则 ===')
    if 'w' in rules:
        print('\n门幅规则:')
        for rule in rules['w'].get('rules', []):
            print(f'  - {rule}')
    if 'l' in rules:
        print('\n衣长/裤长规则:')
        print(f"  - 规则: {rules['l'].get('desc')}")
        print(f"  - 公式: {rules['l'].get('f')}")
        print(f"  - 示例: {rules['l'].get('ex')}")
    if 'wa' in rules:
        print('\n腰围规则:')
        print(f"  - 规则: {rules['wa'].get('desc')}")
        print(f"  - 公式: {rules['wa'].get('f')}")
        print(f"  - 示例: {rules['wa'].get('ex')}")
    if 'plaid' in rules:
        print('\n格子面料规则:')
        print(f"  - 规则: {rules['plaid'].get('desc')}")
        print(f"  - 公式: {rules['plaid'].get('f')}")
        print(f"  - 示例: {rules['plaid'].get('ex')}")

def main():
    if len(sys.argv) < 2:
        print('Usage:')
        print('  python query_fabric.py smart <版型> [尺码] [门幅]')
        print('  python query_fabric.py json  <版型> [尺码] [门幅] [长度调整] [腰围调整] [格子标记] [套装类型]')
        print('  python query_fabric.py calc  <版型> [尺码] [门幅]')
        print('  python query_fabric.py pattern <版型>')
        print('  python query_fabric.py rules')
        print()
        print('  参数说明:')
        print('    版型: 版型编码，如 1KN902、6KN340、6TF018')
        print('    尺码: 40~60码')
        print('    门幅: 面料幅宽，单位cm，如 65、74、130、150')
        print('    长度调整: 衣长/裤长调整量，单位cm（正数增加，负数减少）')
        print('    腰围调整: 腰围调整量，单位cm')
        print('    格子标记: 1=格子面料(+10cm)，0=平板面料(不加量)')
        print('    套装类型: 两件套/套装=单件减20cm，三件套=单件减30cm')
        print()
        print('  示例:')
        print('    python query_fabric.py json 6KN340 54 130 0 0 0')
        print('    python query_fabric.py json 1KN902 48 150 5 10 1')
        return
    command = sys.argv[1]
    if command in ('smart', 'query') and len(sys.argv) >= 3:
        model = sys.argv[2]
        size = sys.argv[3] if len(sys.argv) >= 4 else None
        width = float(sys.argv[4]) if len(sys.argv) >= 5 else None
        smart_query(model, size, width)
    elif command == 'json' and len(sys.argv) >= 3:
        model = sys.argv[2]
        size = sys.argv[3] if len(sys.argv) >= 4 else None
        width = float(sys.argv[4]) if len(sys.argv) >= 5 else None
        length_adj = float(sys.argv[5]) if len(sys.argv) >= 6 else None
        waist_adj = float(sys.argv[6]) if len(sys.argv) >= 7 else None
        is_plaid = bool(int(sys.argv[7])) if len(sys.argv) >= 8 else False
        suit_type = sys.argv[8] if len(sys.argv) >= 9 else None
        result_json = smart_query_json(model, size, width, length_adj, waist_adj, is_plaid, suit_type)
        print(result_json)
    elif command == 'calc' and len(sys.argv) >= 3:
        model = sys.argv[2]
        size = sys.argv[3] if len(sys.argv) >= 4 else None
        width = float(sys.argv[4]) if len(sys.argv) >= 5 else None
        results = query_fabric_calculation(model, size, width)
        if results:
            print(f"=== 面料计算参考表: {model} {' ' + size if size else ''}{' 门幅' + str(width) if width else ''} ===")
            for idx, result in enumerate(results):
                print(f"\n{idx + 1}. {result['source']}")
                data = result['data']
                for k, v in data.items():
                    print(f'  {k}: {v}')
        else:
            print(f"参考表中未找到 {model} {'(' + size + ')' if size else ''} 的数据")
    elif command == 'pattern' and len(sys.argv) >= 3:
        model = sys.argv[2]
        result = query_pattern_rules(model)
        if result:
            print(f"=== 版型规则: {model} ===")
            print(f"版型编码: {result['pattern_code']}")
            for k, v in result['rules'].items():
                if v:
                    print(f'  {k}: {v}')
        else:
            print(f'未找到 {model} 的版型规则')
    elif command == 'rules':
        print_rules()

if __name__ == '__main__':
    main()
