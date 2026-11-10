"""Build one offline entry page and matched-base robustness comparison."""
import csv
from html import escape
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def build_summary():
    output=ROOT/'output/worksheet_benchmark';dataset=ROOT/'benchmarks/worksheet_v1'
    read=lambda name:json.loads((output/name/'metrics.json').read_text())
    strict=read('qwen_reading_v1');normalized=read('qwen_reading_v1_normalized')
    stress=read('qwen_stress_v1');stress_norm=read('qwen_stress_v1_normalized')
    counts=read('qwen_object_counts_v1');counts_norm=read('qwen_object_counts_v1_normalized')
    variants=json.loads((dataset/'stress/manifest.json').read_text())['cases']
    base_ids={c['base_id'] for c in variants};paired=[]
    for mode,base_report,variant_report in [('strict',strict,stress),('engineering_normalized',normalized,stress_norm)]:
        originals=[c for c in base_report['cases'] if c['id'] in base_ids]
        paired.append({'mode':mode,'condition':'original_same_10_bases','correct_expression':sum(c['expression_correct'] for c in originals),'images':10,'independent_questions':10})
        for condition,m in variant_report['conditions'].items():
            paired.append({'mode':mode,'condition':condition,'correct_expression':m['source_expression_accuracy']['correct'],'images':10,'independent_questions':10})
    with (output/'paired_robustness.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,list(paired[0]));writer.writeheader();writer.writerows(paired)
    def ratio(value):return f"{value['correct']} / {value['total']}"
    rows=[('主主题标签匹配（100原题）',ratio(strict['metrics']['topic_accuracy']),ratio(normalized['metrics']['topic_accuracy'])),
          ('算式完整转录（26题）',ratio(strict['metrics']['source_expression_accuracy']),ratio(normalized['metrics']['source_expression_accuracy'])),
          ('格式无效的输出（100原题）',str(strict['metrics']['invalid_outputs']),str(normalized['metrics']['invalid_outputs'])),
          ('可见物品类别 + 数量匹配（8图 / 9组）',f"{counts['exact_visible_count_targets_correct']} / 9",f"{counts_norm['exact_visible_count_targets_correct']} / 9"),
          ('识别出缺少口头题干（1个控制样本）','0 / 1','0 / 1')]
    results_table=''.join('<tr>'+''.join(f'<td>{escape(cell)}</td>' for cell in row)+'</tr>' for row in rows)
    paired_table=''.join(f'<tr><td>{r["mode"]}</td><td>{r["condition"]}</td><td>{r["correct_expression"]} / {r["images"]}</td></tr>' for r in paired)
    html=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Worksheet Reading Lab · 结果总览</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:#192d49;font:16px/1.65 -apple-system,BlinkMacSystemFont,sans-serif}}header{{background:#192d49;color:white;padding:45px max(24px,calc((100vw - 1120px)/2))}}header small{{letter-spacing:.15em;color:#b3c6df}}h1{{font-size:36px;margin:12px 0}}header p{{color:#d3dfef;max-width:930px}}main{{max-width:1170px;margin:auto;padding:25px}}a{{color:#245482}}.links{{display:flex;gap:12px;flex-wrap:wrap}}.links a{{background:white;border:1px solid #cdd9e6;padding:12px 17px;border-radius:8px;text-decoration:none}}section{{background:white;padding:25px;margin:25px 0;border:1px solid #d9e2ed;border-radius:12px}}h2{{margin:0 0 12px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;padding:11px;border-bottom:1px solid #d9e2ed}}.note{{border-left:4px solid #426487;padding:13px 17px;background:#edf2f8}}li{{margin:10px 0}}footer{{font-size:13px;color:#506780;margin:25px 0}}@media(max-width:650px){{h1{{font-size:28px}}section{{padding:15px}}table{{font-size:12px}}td,th{{padding:7px}}}}
</style><header><small>LESSON BUDDY · LOCAL RESEARCH / V1</small><h1>先验证读题，再扩大教学范围。</h1><p>100张网上原始题面与任务 · 22类数学内容 · 23个来源PDF · 30张独立标记的模拟变体。已用本地 Qwen3-VL 4B 跑完第一轮；付费API调用为0。</p></header><main>
<div class="links"><a href="../../benchmarks/worksheet_v1/index.html">浏览100张题面与标注</a><a href="qwen_reading_v1/report.html">严格基线逐题结果</a><a href="qwen_reading_v1_normalized/report.html">格式归一化诊断</a><a href="qwen_object_counts_v1_normalized/report.html">物品计数小样本</a></div>
<section><h2>先看数据和结论的边界</h2><p>80张来自英国KS1测评及练习题，20张来自美国K/1/2数学任务；保留各自年级定义。另有30张模拟变体，复用10道原题。<strong>真实手机照片为0</strong>，这轮不能证明拍照识别已可靠。</p><div class="note">这是独立的广题型读题探针，未替换线上浏览器模型，未改变视频支持范围。主题标签、物品计数、解题理解和视频正确性分别检验；本轮没有“整体识别准确率”。标注尚需独立教师复核。</div></section>
<section><h2>第一轮读题结果</h2><table><thead><tr><th>指标与分母</th><th>严格基线</th><th>工程格式归一化复算</th></tr></thead><tbody>{results_table}</tbody></table><p>右列使用同一批原始输出，仅统一数字字符串/已知数学符号，或将单个物品组包装为列表。没有重新推理，没有使用答案，没有修复错误JSON或改变题意。它用于区分接口问题与内容问题，不能替代严格基线。</p></section>
<section><h2>已经暴露的具体问题</h2><ul><li><strong>缺题干时仍猜题：</strong>面对没有口头问题的梯子图，模型猜测为几何比较题，而未要求补充上下文。</li><li><strong>物品漏数：</strong>橙子图有21个可见橙子，计数探针返回16个。猫贴纸则正确计为12个。可见物品数量与题目要求的隐藏数量是不同标签。</li><li><strong>输出格式不稳定：</strong>原题读题输出有23/100条不符合严格格式；其中9条可通过有限格式归一化恢复，其余继续保留为失败。</li><li><strong>主题与题意不能画等号：</strong>多步骤题可能跨主题；“知道是时间题”不能证明模型读对钟面或排序。开放题需要人工评分。</li></ul></section>
<section><h2>拍照与手写：先看同一10道题的配对结果</h2><table><thead><tr><th>统计口径</th><th>条件</th><th>原式完整转录</th></tr></thead><tbody>{paired_table}</tbody></table><p>这些是同10道开发题的模拟变体，没有新增独立题目；模拟手写是字体与绘制符号，不是真实儿童手写。样本小且仅覆盖算式，不能与100张广题型总体直接比较，也不能推断真实阴影/模糊不会影响识别。<a href="paired_robustness.csv">配对结果CSV</a> · <a href="qwen_stress_v1/report.html">严格变体逐题结果</a> · <a href="qwen_stress_v1_normalized/report.html">归一化变体诊断</a></p></section>
<section><h2>接下来按证据推进</h2><ol><li>先修复通用输出契约和缺题干时的澄清策略，用开发集调试。</li><li>让教师复核题意、物品数量、图形关系；为更多非算式题补充完整标签。</li><li>加入不同设备、光照、倾斜和真实手写的手机照片，并保留全新测试来源。</li><li>再比较浏览器模型、较强本地模型或微调版本；在新留出集上复测后决定接入视频。</li></ol><p>目前并未训练/微调模型；收集新题不会自动改变模型参数。已完成的价值是：建立可复现、可逐题核对的改进依据。</p></section>
<footer>资料来源：<a href="https://www.gov.uk/government/publications/optional-key-stage-1-tests-2026-mathematics-test-materials">STA 2026</a>、<a href="https://www.gov.uk/government/publications/optional-key-stage-1-tests-2025-mathematics-test-materials">STA 2025</a>、<a href="https://tasks.illustrativemathematics.org/content-standards/K">Illustrative Mathematics</a>。混合许可语料仅用于本地非商业capstone研究，未发布到儿童网站。<a href="../../benchmarks/worksheet_v1/ATTRIBUTION.txt">许可与署名</a> · <a href="../../benchmarks/worksheet_v1/README.txt">运行说明</a></footer></main></html>'''
    (output/'index.html').write_text(html)
    facts={'original_images':100,'stress_images':30,'stress_base_questions':10,'topics':22,'real_phone_photos':0,
           'baseline_cases_completed':100,'stress_cases_completed':30,'count_probe_cases_completed':8,
           'count_probe_target_groups':9,'paid_api_requests':0,'production_app_changed':False,
           'independent_teacher_review':False,'training_or_fine_tuning_performed':False,
           'summary_rows':rows,'paired_robustness':paired}
    (output/'summary.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n')
    return output/'index.html'

if __name__=='__main__':print(build_summary())
