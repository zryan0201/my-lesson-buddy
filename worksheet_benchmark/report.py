"""Readable per-case audit, retaining failures and incomplete results."""
import csv
from html import escape
import json
import os
from pathlib import Path

def write_report(report,manifest,root,output):
    m=report['metrics']
    population=escape(manifest['source_population'])
    run_path=output/'run.json'
    run=json.loads(run_path.read_text()) if run_path.exists() else {}
    mode='工程格式归一化复算（沿用原始输出，没有重新推理）' if run.get('mode')=='posthoc_engineering_normalization' else '严格原始输出基线'
    fields=['id','split','topic','status','topic_correct','expression_scored','expression_correct','numeric_hits','numeric_targets','seconds']
    with (output/'case_results.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fields,extrasaction='ignore');writer.writeheader();writer.writerows(report['cases'])
    def ratio(metric):return f"{metric['correct']} / {metric['total']}"
    table=''.join(f'<tr><td>{escape(topic)}</td><td>{ratio(value["topic_accuracy"])}</td><td>{ratio(value["source_expression_accuracy"])}</td><td>{value["runtime_errors"]+value["invalid_outputs"]}</td></tr>' for topic,value in report['topics'].items())
    cases={case['id']:case for case in manifest['cases']}
    details=[]
    for row in sorted(report['cases'],key=lambda row:(row['topic_correct'],row['expression_correct'],row['id'])):
        case=cases[row['id']];pred=row['prediction'];e=case['expected']
        image_path=Path(os.path.relpath(root/case['image'],output)).as_posix()
        badge='需复核' if not row['topic_correct'] or row['expression_scored'] and not row['expression_correct'] else '标签检查通过'
        body=json.dumps({'gold_topic':e['topic'],'gold_expression':e['expression'],'gold_context_required':e['needs_more_context'],
                         'model':pred.get('reading'),'status':pred['status'],'error':pred.get('error')},ensure_ascii=False,indent=2)
        details.append(f'<details><summary>{escape(row["id"])} · {escape(row["topic"])} · {badge}</summary><img loading="lazy" src="{escape(image_path,quote=True)}" alt="题面"><pre>{escape(body)}</pre><a href="{escape(case["source"]["url"],quote=True)}">原始资料</a></details>')
    metrics=escape(json.dumps(m,ensure_ascii=False,indent=2))
    html=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Worksheet reading · baseline report</title><style>
body{{font:16px/1.6 -apple-system,BlinkMacSystemFont,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#192d49;background:#f5f7fa}}h1{{font-size:32px}}.note,details{{background:white;border:1px solid #d9e1eb;border-radius:10px;padding:17px;margin:14px 0}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{text-align:left;padding:8px 12px;border-bottom:1px solid #d9e1eb}}pre{{white-space:pre-wrap;word-break:break-word;font-size:13px;background:#edf2f8;padding:15px}}img{{width:100%;max-height:500px;object-fit:contain;background:white}}summary{{cursor:pointer}}a{{color:#234c78}}
</style><h1>陌生 worksheet：第一轮本地识读基线</h1><p>{escape(mode)} · {m['completed_cases']} / {m['expected_cases']} 已完成 · 固定提示词 · 本地 Qwen3-VL 4B · 0 次付费 API 调用</p>
<div class="note">这是独立的广题型读题探针，不是线上浏览器模型的成绩，也未改变现有视频支持范围。主题标签匹配不能证明题意完全读懂。语料范围：{population}。不包含真实手机拍照；来源公开，可能已出现在预训练中。数字召回只检查部分文字层数字，不代表物品计数准确率。标注尚未经过独立教师复核。</div>
<h2>可自动核对的部分</h2><p>主主题标签匹配：<strong>{ratio(m['topic_accuracy'])}</strong>。原式完整转录：<strong>{ratio(m['source_expression_accuracy'])}</strong>。运行错误 {m['runtime_errors']}；格式无效 {m['invalid_outputs']}；缺失 {m['missing_predictions']}。</p>
<table><thead><tr><th>主题</th><th>主题匹配 / 样本</th><th>原式正确 / 可核对题</th><th>运行/格式错误</th></tr></thead><tbody>{table}</tbody></table>
<h2>逐题核对</h2><p>优先列出标签不匹配的题；它们需要检查模型和人工标注两侧。开放题的解题理解仍需人工评分。</p>{''.join(details)}
<h2>完整统计口径</h2><pre>{metrics}</pre><p><a href="metrics.json">完整结果 JSON</a> · <a href="case_results.csv">逐题 CSV</a> · <a href="predictions.jsonl">模型原始输出</a></p></html>'''
    (output/'report.html').write_text(html)
