"""Анализирует измеренные результаты без синтетических и восстановленных значений."""
from __future__ import annotations
import csv
import json
import math
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
import numpy as np
from scipy.stats import linregress, kruskal, t as student_t
from algorithms.search_methods import search_method
from .experiment_store import read_database
from .campaign_runner import MODEL_REVISION
from algorithms.statevector_limits import MODEL_REVISION as STATEVECTOR_REVISION
from .comparison_analysis import theory_order

def statistics(values):
    values = [float(v) for v in values if v is not None]
    if not values:
        return dict(n=0, mean=None, median=None, stddev=None, minimum=None, maximum=None, ci95_low=None, ci95_high=None)
    mean = float(np.mean(values)); n = len(values)
    std = float(np.std(values, ddof=1)) if n > 1 else None
    margin = float(student_t.ppf(.975, n-1)) * std / math.sqrt(n) if n > 1 else None
    return dict(n=n, mean=mean, median=float(np.median(values)), stddev=std,
                minimum=min(values), maximum=max(values), ci95_low=mean-margin if margin is not None else None,
                ci95_high=mean+margin if margin is not None else None)

def regression(points, expected):
    points=[(x,y) for x,y in points if y is not None and y>0 and math.isfinite(y)]
    result = dict(points=len(points), expected_slope=expected, slope=None, absolute_difference=None,
                  r_squared=None, ci95_low=None, ci95_high=None)
    if len(points) < 2 or len({x for x,y in points}) < 2:
        return result
    fit=linregress([x for x,y in points], [math.log2(y) for x,y in points])
    margin=float(student_t.ppf(.975,len(points)-2))*fit.stderr if len(points)>2 else None
    result.update(slope=float(fit.slope), absolute_difference=abs(float(fit.slope)-expected) if expected is not None else None,
                  r_squared=float(fit.rvalue**2), ci95_low=float(fit.slope-margin) if margin is not None else None,
                  ci95_high=float(fit.slope+margin) if margin is not None else None)
    return result

def write_csv(path, rows):
    fields=list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def analyze_database(database: Path, output: Path, campaign: str | None = None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    entries=read_database(Path(database))
    if campaign:
        entries=[e for e in entries if e.metadata.get('campaign')==campaign]
    if MODEL_REVISION==STATEVECTOR_REVISION and any(entry.record.measurement_version != MODEL_REVISION for entry in entries):
        raise ValueError('Анализ активной серии требует только данные текущей версии вектора амплитуд.')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    groups=defaultdict(list)
    failures=[]
    for entry in entries:
        r=entry.record
        key=(entry.metadata.get('campaign','unlabelled'),entry.metadata.get('group','unlabelled'),
             r.measurement_version,r.experiment_type,('bbht' if search_method(r.method).value == 'grover_bbht' else 'quantum' if r.is_quantum else 'classical'),
             r.n,r.k,r.prefix_blocks,r.sigma_bits,r.rounds,
             json.dumps([r.model,r.link_N,r.first_level_N,r.parameter_strategy,
                         r.target_probability if r.parameter_strategy != 'theoretical' else None,
                         r.attack_diamond_digest,r.attack_prefix_state,r.attack_message_digest,
                         r.attack_trials_limit,r.amplitude_backend],ensure_ascii=False), r.search_configuration)
        groups[key].append(entry)
        if r.status!='Завершено':failures.append(entry.to_dict())
    rows=[]
    for key,members in sorted(groups.items()):
        camp,group,version,stage,method,n,k,p,s,rounds,configuration,search_configuration=key
        good=[e.record for e in members if e.record.status=='Завершено']
        row=dict(campaign=camp,group=group,measurement_version=version,stage=stage,method=method,
                 n=n,k=k,prefix_blocks=p,s=s,rounds=rounds,configuration=configuration,search_configuration=search_configuration,successful=len(good),failed=sum(e.record.status=='Ошибка' for e in members),
                 interrupted=sum(e.record.status=='Остановлено' for e in members),skipped=sum(e.record.status=='Пропущено' for e in members))
        for metric,values in dict(queries=[r.algorithmic_queries for r in good],time=[r.elapsed_seconds for r in good],
                                 simulator_g=[r.quantum_simulator_hash_evaluations if r.is_quantum else r.algorithmic_queries for r in good],
                                 qram_peak=[r.quantum_qram_peak_entries for r in good],qram_total=[r.quantum_qram_total_entries for r in good],
                                 marked=[r.link_marked_count for r in good if r.is_quantum],
                                 marked_per_attempt=[r.link_marked_count/r.link_attempts for r in good if r.is_quantum and r.link_marked_count is not None and r.link_attempts],
                                 attempts=[r.link_attempts for r in good if r.is_quantum],
                                 statevector_elements=[r.statevector_elements_processed for r in good],
                                 statevector_time=[r.statevector_seconds for r in good],
                                 norm_error=[r.statevector_norm_error_max for r in good],
                                 grover_attempts=[r.grover_attempts for r in good],
                                 success_probability=[r.success_probability_sum / r.grover_attempts for r in good if r.success_probability_sum is not None and r.grover_attempts],
                                 matching_attempts=[r.quantum_layer_attempts for r in good],
                                 verification_g=[r.verification_hash_evaluations for r in good],
                                 independent_verification_g=[r.independent_verification_hash_evaluations for r in good]).items():
            row.update({metric+'_'+name:value for name,value in statistics(values).items()})
        row['theoretical_order'],row['theoretical_note']=theory_order(members[0].record)
        row['mean_over_theoretical_order']=row['queries_mean']/row['theoretical_order'] if row['queries_mean'] is not None and row['theoretical_order'] else None
        unsuccessful = [e.record for e in members if e.record.status in ('Ошибка', 'Остановлено')]
        for metric, values in (('failure_time', [r.elapsed_seconds for r in unsuccessful]),
                               ('failure_queries_lower_bound', [r.algorithmic_queries for r in unsuccessful]),
                               ('failure_simulator_g_lower_bound', [r.quantum_simulator_hash_evaluations for r in unsuccessful]),
                               ('failure_statevector_elements_lower_bound', [r.statevector_elements_processed for r in unsuccessful])):
            row.update({metric + '_' + name: value for name, value in statistics(values).items()})
        rows.append(row)
    _three_method_charts(rows, output)
    diagnostics = statevector_diagnostics(groups, output)
    diamond=[r for r in rows if r['stage']=='diamond'];linking=[r for r in rows if r['stage']=='herding']
    write_csv(output/'diamond_scaling.csv',diamond);write_csv(output/'linking_scaling.csv',linking)
    write_csv(output/'sigma_comparison.csv',[r for r in rows if r['group'] in ('D','D_extra')])
    (output/'failures.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2),encoding='utf-8')
    # Строит регрессию по средним при разных значениях оси и одинаковых остальных параметрах.
    fits=[]
    for camp in sorted({r['campaign'] for r in rows}):
        for stage,group,ks in [('diamond','A',[7]),('herding','C',[3,5,7,8])]:
            for k in ks:
                for method in ('classical','quantum','bbht'):
                    selected=[r for r in rows if r['campaign']==camp and r['group']==group and r['stage']==stage
                              and r['method']==method and r['k']==k and r['s']==0 and r['prefix_blocks']==1
                              and r['rounds']==12 and r['measurement_version']==MODEL_REVISION and r['queries_mean'] is not None and r['queries_mean']>0]
                    for configuration, profile in sorted({(row['configuration'], row['search_configuration']) for row in selected}):
                        current_rows = [row for row in selected if row['configuration'] == configuration and row['search_configuration'] == profile]
                        points=sorted((r['n'],r['queries_mean']) for r in current_rows)
                        expected=None if method=='bbht' else (1/3 if method!='classical' else .5) if stage=='diamond' else (.5 if method!='classical' else 1.)
                        fit=dict(campaign=camp,stage=stage,method=method,k=k,axis='n',configuration=configuration,**regression(points,expected))
                        fits.append(fit)
                        if points:
                            fig,ax=plt.subplots(figsize=(6.4,3.7));ax.plot([x for x,y in points],[math.log2(y) for x,y in points],'o-')
                            ax.set_xticks([x for x,y in points])
                            for r in current_rows:
                                low,high=r['queries_ci95_low'],r['queries_ci95_high']
                                if low is not None and low>0 and high is not None:
                                    y=math.log2(r['queries_mean'])
                                    ax.errorbar(r['n'],y,yerr=[[y-math.log2(low)],[math.log2(high)-y]],fmt='none',capsize=3,color='steelblue')
                            ax.set(xlabel=r'$n$ (размер части хэш-кода, бит)',ylabel=r'$\log_2(\overline{Q})$, 95% ДИ',title=f"{'Построение алмаза' if stage=='diamond' else 'Поиск связующего блока'} · {'Классический алгоритм' if method=='classical' else search_method(method).label} · k={k}")
                            ax.grid(alpha=.25);fig.tight_layout();fig.savefig(output/f'{stage}_{method}_k{k}.png',dpi=160);plt.close(fig)
    write_csv(output/'theory_comparison.csv',fits)
    for camp in sorted({r['campaign'] for r in rows}):
        for stage in ('diamond','herding'):
            fig,ax=plt.subplots(figsize=(7,4))
            for method in ('classical','quantum','bbht'):
                subset=sorted([r for r in rows if r['campaign']==camp and r['group']=='D' and r['stage']==stage and r['method']==method and r['queries_mean'] is not None and r['queries_mean']>0],key=lambda r:r['s'])
                if subset and len({(row['configuration'],row['measurement_version']) for row in subset}) == 1:ax.plot([r['s'] for r in subset],[r['queries_mean'] for r in subset],'o-',label='Классический алгоритм' if method=='classical' else search_method(method).label)
            if ax.lines:
                ax.legend();ax.set(xlabel=r'$s$ (размер части контрольной суммы $\Sigma_s$, бит)',ylabel='Среднее число запросов',title=f"Sigma: {'алмаз' if stage=='diamond' else 'связующий блок'}, n=16, k=7")
                ax.grid(alpha=.25);fig.tight_layout();fig.savefig(output/f'{camp}_sigma_{stage}.png',dpi=160)
            plt.close(fig)
        for group,axis,title in [('B','k','Зависимость от глубины алмаза, n=24'),('E','prefix_blocks','Длина префикса, n=16, k=7, s=8')]:
            fig,ax=plt.subplots(figsize=(7,4))
            for method in ('classical','quantum','bbht'):
                subset=sorted([r for r in rows if r['campaign']==camp and r['group']==group and r['stage']=='diamond' and r['method']==method and r['queries_mean'] is not None and r['queries_mean']>0],key=lambda r:r[axis])
                if subset and len({row['configuration'] for row in subset}) == 1:
                    xs=[r[axis] for r in subset]
                    ax.plot(xs,[math.log2(r['queries_mean']) for r in subset],'o-',label=('Классический' if method=='classical' else search_method(method).label)+' · измерения')
                    if group=='B' and all(r['theoretical_order'] for r in subset):ax.plot(xs,[math.log2(r['theoretical_order']) for r in subset],'--',label=('Классический' if method=='classical' else search_method(method).label)+' · асимптотический порядок')
            if ax.lines:
                ax.legend(fontsize=8);ax.set_xticks(xs);ax.set(xlabel='$k$ (глубина алмаза)' if axis=='k' else 'Блоков префикса',ylabel=r'$\log_2(\overline{Q})$',title=title)
                ax.grid(alpha=.25);fig.tight_layout();fig.savefig(output/f'{camp}_{group}.png',dpi=160)
            plt.close(fig)
    sigma_fits=[]
    for camp in sorted({r['campaign'] for r in rows}):
        for stage in ('diamond','herding'):
            for method in ('classical','quantum','bbht'):
                selected=[r for r in rows if r['campaign']==camp and r['group']=='D' and r['stage']==stage
                          and r['method']==method and r['queries_mean'] is not None and r['queries_mean']>0]
                if not selected or len({row['configuration'] for row in selected}) != 1:continue
                points=sorted((r['s'],r['queries_mean']) for r in selected)
                distributions=defaultdict(list)
                for e in entries:
                    r=e.record
                    if e.metadata.get('campaign')==camp and e.metadata.get('group')=='D' and r.experiment_type==stage and (('bbht' if search_method(r.method).value == 'grover_bbht' else 'quantum' if r.is_quantum else 'classical'))==method and r.status=='Завершено' and r.algorithmic_queries is not None:
                        distributions[r.sigma_bits].append(r.algorithmic_queries)
                hstat=pvalue=None
                if len(distributions)>1:
                    try:
                        test=kruskal(*distributions.values());hstat=float(test.statistic);pvalue=float(test.pvalue)
                    except ValueError:pass  # Для одинаковых значений статистика Краскела — Уоллиса не определена.
                sigma_fits.append(dict(campaign=camp,stage=stage,method=method,**regression(points,0.),
                                       max_mean_over_min_mean=max(y for x,y in points)/min(y for x,y in points),
                                       kruskal_h=hstat,kruskal_p=pvalue,bonferroni_threshold=.05/4,
                                       rejected_after_bonferroni=pvalue<.05/4 if pvalue is not None else None))
    write_csv(output/'sigma_dependence.csv',sigma_fits)
    result=dict(records=len(entries),successful=sum(e.record.status=='Завершено' for e in entries),
                failed=sum(e.record.status=='Ошибка' for e in entries),interrupted=sum(e.record.status=='Остановлено' for e in entries),
                skipped=sum(e.record.status=='Пропущено' for e in entries),statevector_diagnostics=diagnostics,regressions=fits,sigma_dependence=sigma_fits,output=str(output.resolve()))
    (output/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    text=['# Анализ реальных экспериментов','',f"Записей: {len(entries)}. Успешных: {result['successful']}. Ошибок: {result['failed']}. Остановленных: {result['interrupted']}. Пропущенных: {result['skipped']}.",'',
          'Старые и новые версии счётчиков анализируются раздельно. Неизвестные значения остаются пустыми в CSV; ошибки не заменены успешными повторами. Статистика Q условна по успешным запускам. Стоимость неудачного запуска не включена, если backend не экспортировал счётчики.','',
          'Время включает построение или атаку и независимый replay. Квантовое время относится к CPU-симулятору. qRAM peak – максимум размера таблицы в одной попытке; total – сумма подготовленных записей за все попытки. Для старых записей peak не восстановлен.','',
          '| Этап | Метод | k | Наклон | Ожидаемый | Разность | R² | Точек | 95% CI |','|---|---|---:|---:|---:|---:|---:|---:|---|']
    def fmt(v):return '–' if v is None else f'{v:.5g}'
    for f in fits:
        text.append(f"| {f['stage']} | {f['method']} | {f['k']} | {fmt(f['slope'])} | {fmt(f['expected_slope'])} | {fmt(f['absolute_difference'])} | {fmt(f['r_squared'])} | {f['points']} | {fmt(f['ci95_low'])}; {fmt(f['ci95_high'])} |")
    text+=['','Неположительные Q не включаются в логарифмическую регрессию; исходные значения остаются в CSV. Регрессии log₂(среднего Q) по n выполняются при фиксированном k. CI использует t-распределение и стандартную модель независимых остатков линейной регрессии; при двух точках CI отсутствует, R²=1 не доказывает теорию. Для linking основной ряд k=7 содержит три значения n. Прочие k приводятся отдельно, без смешивания зависимостей.','',
           'Среднее, медиана, выборочное stddev, min/max, t-интервал среднего, успехи и ошибки, marked elements и attempts представлены в CSV. Интервалы среднего не гарантируют покрытие для сильно асимметричных распределений при малых выборках. Один reused diamond на набор linking ограничивает обобщение на все возможные структуры.','',
           'Для Sigma таблица и графики показывают реальную зависимость от s; визуальная близость не является доказательством равномерности. Статистический диагностический тест вынесен в sigma_distribution.json. Теоретические порядки приведены без неизвестных констант и округлений L/S.']
    text += ['', 'Модельные итерации задаются теоретическим бюджетом одного ожидаемого решения; близкий к теории наклон Q не является независимым доказательством её показателя. Эмпирические успехи получены измерением полного вектора амплитуд. Вероятность из амплитуд, успешные и неудачные измерения, успехи паросочетания и стоимость повторов приведены в statevector_diagnostics.csv. Wilson-интервалы являются диагностическими и предполагают независимость испытаний; повторное использование qRAM может нарушать это предположение.', '', 'Отдельные столбцы failure_* содержат только известные затраты неуспешных запусков; частичные счётчики являются нижними границами и не включают работу незавершённого дочернего процесса. Невыполненные задания не учитываются как успешные эксперименты.']
    text+=['','Sigma: log₂(mean Q) по s (ожидаемый наклон 0). Kruskal–Wallis сравнивает распределения Q для семи s; четыре проверки используют Bonferroni 0.05/4. Оба результата диагностические, без доказательства независимости случайного оракула.']
    for f in sigma_fits:
        text.append(f"- {f['stage']} {f['method']}: slope={fmt(f['slope'])}, CI=[{fmt(f['ci95_low'])}, {fmt(f['ci95_high'])}], max/min средних={fmt(f['max_mean_over_min_mean'])}, KW p={fmt(f['kruskal_p'])}, отклонение после поправки={f['rejected_after_bonferroni']}.")
    (output/'summary.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    return result


def wilson_interval(successes, trials):
    """Возвращает диагностический интервал Уилсона для наблюдаемой доли успехов."""
    if not trials:
        return None, None
    z = 1.959963984540054
    proportion = successes / trials
    denominator = 1 + z * z / trials
    center = (proportion + z * z / (2 * trials)) / denominator
    radius = z * math.sqrt(proportion * (1 - proportion) / trials + z * z / (4 * trials * trials)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def statevector_diagnostics(groups, output):
    """Собирает измерения амплитуд, успехи поиска и паросочетания вместе с ценой неудач."""
    import matplotlib.pyplot as plt
    rows = []
    for key, members in sorted(groups.items()):
        camp, group, version, stage, method, n, k, p, s, rounds, configuration, search_configuration = key
        if method == 'classical':
            continue
        measured = [e.record for e in members if e.record.grover_attempts is not None]
        attempts = sum(r.grover_attempts for r in measured)
        successes = sum(r.quantum_grover_successes or 0 for r in measured)
        matching_attempts = sum(r.quantum_layer_attempts or 0 for r in measured)
        matching_successes = sum(r.matching_successes or 0 for r in measured)
        low, high = wilson_interval(successes, attempts)
        match_low, match_high = wilson_interval(matching_successes, matching_attempts)
        probabilities = [r.success_probability_sum for r in measured if r.success_probability_sum is not None]
        row = dict(campaign=camp, group=group, stage=stage, method=method, configuration=configuration, search_configuration=search_configuration, n=n, k=k, prefix_blocks=p, s=s,
                   attempts=attempts, successful_measurements=successes, unsuccessful_measurements=attempts-successes,
                   empirical_success_probability=successes/attempts if attempts else None,
                   amplitude_success_probability=sum(probabilities)/attempts if attempts and len(probabilities)==len(measured) else None,
                   wilson95_low=low, wilson95_high=high,
                   matching_attempts=matching_attempts, successful_matchings=matching_successes,
                   matching_success_probability=matching_successes/matching_attempts if matching_attempts else None,
                   matching_wilson95_low=match_low, matching_wilson95_high=match_high,
                   total_statevector_elements=sum(r.statevector_elements_processed or 0 for r in measured),
                   total_statevector_seconds=sum(r.statevector_seconds or 0 for r in measured),
                   total_simulator_hash_evaluations=sum(r.quantum_simulator_hash_evaluations or 0 for r in measured),
                   max_norm_error=max((r.statevector_norm_error_max or 0 for r in measured), default=None),
                   completed_runs=sum(e.record.status=='Завершено' for e in members),
                   failed_runs=sum(e.record.status=='Ошибка' for e in members),
                   not_executed_runs=sum(e.record.status=='Пропущено' for e in members))
        rows.append(row)
    write_csv(output / 'statevector_diagnostics.csv', rows)
    for stage, group in (('diamond', 'A'), ('herding', 'C')):
        selected = sorted([r for r in rows if r['stage']==stage and r['group']==group and r['method']=='quantum' and r['k']==7 and r['s']==0 and r['attempts']], key=lambda r:r['n'])
        if not selected:
            continue
        fig, ax = plt.subplots(figsize=(7, 4))
        x = [r['n'] for r in selected]
        y = [r['empirical_success_probability'] for r in selected]
        ax.errorbar(x, y, yerr=[[r['empirical_success_probability']-r['wilson95_low'] for r in selected], [r['wilson95_high']-r['empirical_success_probability'] for r in selected]], fmt='o-', capsize=3, label='Доля успешных измерений, 95% ДИ')
        ax.plot(x, [r['amplitude_success_probability'] for r in selected], 's--', label='Вероятность из амплитуд')
        ax.set(xlabel='n, бит', ylabel='Вероятность', title=('Построение алмаза' if stage=='diamond' else 'Связывающий блок')+' · k=7', ylim=(0, 1.03))
        ax.set_xticks(x); ax.grid(alpha=.25); ax.legend(fontsize=8); fig.tight_layout()
        fig.savefig(output / f'{stage}_empirical_success.png', dpi=160); plt.close(fig)
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
        axes[0].plot(x, [r['total_statevector_elements']/r['completed_runs'] if r['completed_runs'] else None for r in selected], 'o-')
        axes[0].set(xlabel='n, бит', ylabel='Посещений на успешный запуск', title='Совокупная работа, включая неудачи')
        axes[1].plot(x, [r['total_statevector_seconds']/r['completed_runs'] if r['completed_runs'] else None for r in selected], 'o-')
        axes[1].set(xlabel='n, бит', ylabel='Секунд на успешный запуск', title='Совокупное время, включая неудачи')
        for ax in axes: ax.grid(alpha=.25); ax.set_xticks(x)
        fig.tight_layout(); fig.savefig(output / f'{stage}_statevector_cost.png', dpi=160); plt.close(fig)
        if stage == 'diamond':
            fig, ax = plt.subplots(figsize=(7, 4))
            y = [r['matching_success_probability'] for r in selected]
            ax.errorbar(x, y, yerr=[[value-r['matching_wilson95_low'] for value,r in zip(y,selected)], [r['matching_wilson95_high']-value for value,r in zip(y,selected)]], fmt='o-', capsize=3)
            ax.set(xlabel='n, бит', ylabel='Доля успешных паросочетаний, 95% ДИ', title='Завершение одного уровня · k=7', ylim=(0, 1.03))
            ax.set_xticks(x); ax.grid(alpha=.25); fig.tight_layout()
            fig.savefig(output / 'diamond_matching_success.png', dpi=160); plt.close(fig)
    return rows


def _three_method_charts(rows, output):
    """Сравнивает средние трёх методов только внутри одной конфигурации и этапа."""
    import matplotlib.pyplot as plt
    grouped = defaultdict(list)
    for row in rows:
        key = tuple(row[key] for key in ('campaign','group','stage','measurement_version','n','k','prefix_blocks','s','rounds','configuration'))
        grouped[key].append(row)
    colors = dict(classical='#2563EB', quantum='#6D5DD3', bbht='#059669')
    markers = dict(classical='o', quantum='s', bbht='^')
    for index, (key, values) in enumerate(grouped.items()):
        if len({row['method'] for row in values}) < 2:
            continue
        fig, ax = plt.subplots(figsize=(8, 4))
        for row in values:
            if row['queries_mean'] is not None:
                method = row['method']
                ax.scatter(method, row['queries_mean'], color=colors[method], marker=markers[method], label=search_method(method).label)
        ax.set(ylabel='Среднее число запросов', title=f'{key[2]} · n={key[4]}, k={key[5]}, s={key[7]} · {key[3]}')
        ax.legend(fontsize=8); ax.grid(alpha=.2); fig.tight_layout()
        fig.savefig(output / f'three_methods_{index}.png', dpi=160); plt.close(fig)
