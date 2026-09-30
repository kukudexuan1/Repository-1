"""
快速参考：查看E1实验结果
"""
import pandas as pd
import json
from pathlib import Path

# 设置路径
ANALYSIS_DIR = Path(__file__).parent

def show_e1_summary():
    """显示E1实验概要"""
    print("=" * 60)
    print("E1实验结果概要")
    print("=" * 60)
    
    # 读取E1数据
    e1 = pd.read_csv(ANALYSIS_DIR / 'E1_runs_corrected.csv')
    
    print(f"\n总运行数: {len(e1)}")
    print(f"有效运行数: {e1['analysis_eligible'].sum()}")
    print(f"\n条件分布:")
    print(e1['meta.condition'].value_counts())
    
    print(f"\n{'='*60}")
    print("关键指标 (按条件)")
    print("=" * 60)
    
    # 关键指标
    metrics = [
        'out.strategy_metrics.keyword.mrr',
        'out.strategy_metrics.keyword.p@1',
        'out.strategy_metrics.exact_id.mrr',
        'out.strategy_metrics.exact_id.p@1',
        'out.strategy_metrics.rag.mrr',
        'out.strategy_metrics.rag.p@1',
    ]
    
    for metric in metrics:
        if metric in e1.columns:
            print(f"\n{metric}:")
            summary = e1.groupby('meta.condition')[metric].agg(['mean', 'std', 'count'])
            print(summary)


def show_statistical_results():
    """显示统计测试结果"""
    print("\n" + "=" * 60)
    print("E1统计测试结果")
    print("=" * 60)
    
    # 读取统计结果
    with open(ANALYSIS_DIR / 'statistical_tests_results.json', 'r', encoding='utf-8') as f:
        stats = json.load(f)
    
    # 筛选E1结果
    e1_stats = [s for s in stats if s['experiment_id'] == 'E1']
    
    print(f"\n总比较数: {len(e1_stats)}")
    
    # 显著性结果
    significant = [s for s in e1_stats if s.get('significant_holm', False)]
    print(f"显著差异数: {len(significant)}")
    
    # 详细结果
    print("\n指标比较 (B1 vs P):")
    print("-" * 60)
    
    df = pd.DataFrame(e1_stats)
    if not df.empty:
        display_cols = ['metric', 'mean_baseline', 'mean_condition', 
                       'absolute_difference', 'p_value_holm', 'significant_holm']
        available_cols = [col for col in display_cols if col in df.columns]
        print(df[available_cols].to_string(index=False))


def show_condition_summary():
    """显示条件汇总"""
    print("\n" + "=" * 60)
    print("条件级别汇总")
    print("=" * 60)
    
    summary = pd.read_csv(ANALYSIS_DIR / 'condition_summary.csv')
    e1_summary = summary[summary['experiment_id'] == 'E1']
    
    if not e1_summary.empty:
        print("\n基本信息:")
        print(e1_summary[['experiment_id', 'condition', 'n_runs', 'n_units']].to_string(index=False))
        
        # 显示关键指标均值
        metric_cols = [col for col in e1_summary.columns if col.endswith('.mean')]
        if metric_cols:
            print("\n关键指标均值:")
            display_df = e1_summary[['condition'] + metric_cols[:5]]  # 显示前5个指标
            print(display_df.to_string(index=False))


def main():
    """主函数"""
    try:
        show_e1_summary()
        show_statistical_results()
        show_condition_summary()
        
        print("\n" + "=" * 60)
        print("数据文件位置:")
        print("=" * 60)
        print(f"E1运行数据: {ANALYSIS_DIR / 'E1_runs_corrected.csv'}")
        print(f"统计结果: {ANALYSIS_DIR / 'statistical_tests_results.csv'}")
        print(f"条件汇总: {ANALYSIS_DIR / 'condition_summary.csv'}")
        print(f"详细文档: {ANALYSIS_DIR / 'E1_README.md'}")
        
    except FileNotFoundError as e:
        print(f"\n错误: 找不到文件 {e.filename}")
        print("请先运行以下命令生成数据:")
        print("  python e1_result_generator.py")
        print("  python aggregate_results.py")
        print("  python statistical_tests.py")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
