"""打印 rng_logs 目录中的 OCR 数据，方便复制到 ten-lines 网页调试。

用法: python print_rng_logs.py <log_dir_name>

示例: python print_rng_logs.py 20260514_021926_Ditto
"""
import sys, os, json, glob, re

def main():
    if len(sys.argv) < 2:
        print("用法: python print_rng_logs.py <log_dir_name>")
        sys.exit(1)

    log_dir = sys.argv[1]

    files = glob.glob(os.path.join(log_dir, '*.json'))
    if not files:
        print(f"目录中无 .json 文件: {log_dir}")
        sys.exit(1)

    # 按 attempt 分组
    attempts = {}
    for fn in files:
        basename = os.path.basename(fn)
        m = re.match(r'(\d+)_(CAUGHT_INFO|CAUGHT_IV|ELEVATED_\d+)\.json', basename)
        if not m:
            continue
        aid = int(m.group(1))
        tag = m.group(2)
        with open(fn, 'r', encoding='utf-8') as f:
            entry = json.load(f)
        if aid not in attempts:
            attempts[aid] = {'info': None, 'iv': None, 'elevated': []}
        if tag == 'CAUGHT_INFO':
            attempts[aid]['info'] = entry
        elif tag == 'CAUGHT_IV':
            attempts[aid]['iv'] = entry
        elif tag.startswith('ELEVATED_'):
            attempts[aid]['elevated'].append((int(tag.split('_')[1]), entry))

    for aid in sorted(attempts):
        data = attempts[aid]
        if not data['info'] or not data['iv']:
            continue

        info = data['info']['ocr_result']
        iv = data['iv']['ocr_result']
        pokemon = data['info'].get('pokemon', '?')

        print(f"#{aid}: pokemon: {pokemon}, nature: {info.get('nature','?')}, "
              f"gender: {info.get('gender','?')}, ability: {iv.get('ability','?')}")

        # 第一行来自 CAUGHT_IV
        lines = []
        def fmt_obs(ocr):
            return f"{ocr.get('level','?')} {ocr.get('hp','?')} {ocr.get('attack','?')} " \
                   f"{ocr.get('defense','?')} {ocr.get('sp_atk','?')} {ocr.get('sp_def','?')} {ocr.get('speed','?')}"

        lines.append(fmt_obs(iv))

        # 后续行来自 ELEVATED_01, ELEVATED_02, ...
        for _, entry in sorted(data['elevated']):
            lines.append(fmt_obs(entry['ocr_result']))

        print("ivs_observation:")
        for line in lines:
            print(line)
        print()


if __name__ == '__main__':
    main()
