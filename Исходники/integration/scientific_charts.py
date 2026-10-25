"""Строит согласованные спецификации научных графиков и воспроизводимые печатные экспорты."""

from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
import csv
import hashlib
import json
import json
import math
from pathlib import Path

from scipy.stats import linregress

from algorithms.search_methods import SearchMethod
from .comparison_analysis import METHOD_NAMES, STAGES, metric_value, canonical, SUCCESS

COLORS={SearchMethod.CLASSICAL:'#1C5BC4',SearchMethod.GROVER_FIXED:'#4F96E3',SearchMethod.GROVER_BBHT:'#8BB9E7'}


TITLES = dict(queries_n='Количество запросов от n', theory='Теория и эксперимент: показатель α',
              speedup='Преимущество по запросам', components='Вклад этапов полной атаки', depth='Влияние глубины k',
              optimal='Оптимальная сложность полной атаки', sigma='Влияние размера части контрольной суммы s',
              model_vs_actual='Модельные запросы и вычисления ГОСТ', dispersion='Разброс результатов',
              evaluations_n='Вычисления функции сжатия от n', runtime_n='Время выполнения от n')
THESIS_GRAPHS = [(f'{stage}_{kind}', kind, stage) for stage in ('diamond', 'herding') for kind in ('queries_n', 'theory', 'speedup')] + [
    ('full_queries', 'queries_n', 'full'), ('full_components', 'components', 'full'), ('full_depth', 'depth', 'full'),
    ('full_optimal', 'optimal', 'full'), ('gost_sigma', 'sigma', 'full'), ('gost_costs', 'model_vs_actual', 'full')]


def axis_for(graph):
    return {'sigma': 's', 'depth': 'k'}.get(graph, 'n')


def options_for(options, graph, stage):
    return replace(options, graph=graph, stage=stage, axis=axis_for(graph), metric='queries',
                   presentation='speedup' if graph == 'speedup' else 'dispersion' if graph == 'dispersion' else 'complexity',
                   theory_ratio=False, filters=tuple((k, v) for k, v in options.filters if k not in ('n', 'k', 's')))


def _hover(group):
    config = group.configuration
    return f"n={config['n']} · k={config['k']} · s={config['s']}<br>Среднее: {group.summary.mean}<br>Медиана: {group.summary.median}<br>Запусков: {group.summary.count} · успешных: {group.successful}/{group.total}"


def _line_series(result):
    """Соединяет совместимые точные модели амплитуд без объединения их измерений."""
    series=defaultdict(list)
    for group in result.groups:
        key=group.series_key
        if result.options.presentation in ('complexity','speedup','dispersion') and result.options.effective_metric!='runtime':
            profile=dict(group.profile)
            if profile.get('amplitude_backend') in ('dense-statevector','dense+exact-symmetric','exact-symmetric'):
                profile['amplitude_backend']='exact-grover'
                decoder=json.JSONDecoder();remaining=key;parts=[]
                while remaining:
                    segment,end=decoder.raw_decode(remaining);remaining=remaining[end:].lstrip()
                    stored=json.loads(segment[2])
                    if stored.get('amplitude_backend') in ('dense-statevector','dense+exact-symmetric','exact-symmetric'):stored['amplitude_backend']='exact-grover'
                    segment[2]=canonical(stored);parts.append(canonical(segment))
                key=''.join(parts)
        series[key].append(group)
    output={}
    for key,groups in series.items():
        if len({g.x for g in groups})==len(groups):output[key]=groups
        else:
            for group in groups:output.setdefault(group.series_key,[]).append(group)
    return output


def chart_spec(result, scale='auto', dark=False, distribution='auto', focus=None):
    graph = result.options.graph
    title = TITLES.get(graph, graph)
    traces, rows, notes = [], [], []
    groups = result.groups
    series = _line_series(result)
    for group in result.groups:
        for item in group.observations:
            rows.append(dict(id=item.uid, method=METHOD_NAMES[group.method], stage=result.options.stage,
                        n=item.record.n, k=item.record.k, s=item.record.sigma_bits, seed=item.metadata.get('seed'),
                        trial=item.metadata.get('trial'), status=item.record.status, verified=item.metadata.get('verified'),
                        protocol=item.record.search_protocol, attempt_policy=item.metadata.get('attempt_policy'),
                        Q=metric_value(item.record, 'queries'), g=metric_value(item.record, 'evaluations'),
                        seconds=item.record.elapsed_seconds, group=group.identity, mean=group.summary.mean,
                        median=group.summary.median, count=group.summary.count, ci_low=group.ci_low, ci_high=group.ci_high,
                        Q_diamond=item.metadata.get('stages',{}).get('diamond',{}).get('queries'),
                        Q_link=item.metadata.get('stages',{}).get('herding',{}).get('queries'),
                        g_diamond=item.metadata.get('stages',{}).get('diamond',{}).get('evaluations'),
                        g_link=item.metadata.get('stages',{}).get('herding',{}).get('evaluations'),
                        plotted_value=group.value, source_ids=';'.join(group.source_ids), baseline_mean=group.baseline_mean,
                        baseline_count=group.baseline_count))
    xlabel = {'n': 'Размер части хэш-кода n, бит', 'k': 'Глубина алмазной структуры k', 's': 'Размер части контрольной суммы s, бит'}[result.options.effective_axis]
    ylabel = 'Преимущество Q класс. / Q квант.' if graph == 'speedup' else {'runtime': 'Время симулятора / выполнения, с', 'evaluations': 'Вычисления функции сжатия g', 'memory': 'Пиковых записей qRAM'}.get(result.options.effective_metric, 'Количество запросов Q')
    shapes = []
    if graph == 'optimal':
        xlabel,ylabel='Метод','Показатель роста α полной атаки'
        optimized=defaultdict(list)
        for group in groups:
            divisor=3 if group.method is SearchMethod.CLASSICAL else 7
            if not all(o.metadata.get('depth_policy') in ('optimal','theoretical_optimal') for o in group.observations):continue
            if abs(group.configuration['k']-group.configuration['n']/divisor)>1:continue
            config={k:v for k,v in group.configuration.items() if k not in ('n','k')}
            optimized[canonical((config,group.profile,group.method.value))].append(group)
        for values in optimized.values():
            positive=[g for g in values if g.value is not None and g.value>0]
            if len({g.x for g in positive})<3 or len({g.configuration['k'] for g in positive})<2 or len({g.x for g in positive})!=len(positive):continue
            fit=linregress([g.x for g in positive],[math.log2(g.value) for g in positive])
            method=positive[0].method;expected=2/3 if method is SearchMethod.CLASSICAL else 3/7
            traces.append(dict(type='bar',x=[METHOD_NAMES[method]],y=[fit.slope],name=METHOD_NAMES[method],marker=dict(color=COLORS[method]),
                               text=[f'α={fit.slope:.3f} · {len(positive)} точек'],textposition='outside',hovertemplate='α=%{y:.10g}<extra></extra>'))
            shapes.append(dict(type='line',xref='paper',x0=0,x1=1,y0=expected,y1=expected,line=dict(color=COLORS[method],dash='dash',width=1.5)))
            notes.append(f'{METHOD_NAMES[method]}: α={fit.slope:.4f}, ориентир {expected:.4f}; точек n: {len(positive)}; использован явно записанный протокол k(n).')
            for row in rows:
                if row['group'] in {g.identity for g in positive}:row.update(alpha=fit.slope,regression_points=len(positive),theoretical_alpha=expected)
        notes.append('Ориентиры оптимальной полной атаки: α = 2/3 для классического метода и α = 3/7 для квантовых методов; требуется обоснованный выбор k(n).')
        if not traces:notes.append('В журнале нет достаточных измерений с подтверждённым протоколом выбора оптимальной глубины k(n); регрессия при фиксированном k здесь не используется.')
    elif graph == 'theory' and result.options.stage == 'full':
        notes.append('Фиксированная глубина k не проверяет оптимальные показатели полной атаки; выберите график оптимальной сложности.')
    elif graph == 'theory':
        xlabel, ylabel = 'Метод', 'Показатель роста α в log₂(Q) = αn + C'
        for values in series.values():
            values = sorted(values, key=lambda g: g.x)
            positive = [g for g in values if g.value is not None and g.value > 0]
            if len({g.x for g in positive}) < 3:
                notes.append('Для регрессии нужны не менее трёх различных n при одинаковых остальных параметрах.')
                continue
            fit = linregress([g.x for g in positive], [math.log2(g.value) for g in positive])
            method = positive[0].method
            expected = (0.5 if method is SearchMethod.CLASSICAL else 1/3) if result.options.stage == 'diamond' else (1 if method is SearchMethod.CLASSICAL else .5)
            name = METHOD_NAMES[method]
            traces.append(dict(type='bar', x=[name], y=[fit.slope], name=name, marker=dict(color=COLORS[method]),
                               text=[f'α = {fit.slope:.3f} · {len(positive)} точек'], textposition='outside',
                               hovertemplate=f'{name}<br>α={fit.slope:.8g}<br>Точек: {len(positive)}<br>R²={fit.rvalue**2:.5f}<extra></extra>'))
            shapes.append(dict(type='line', xref='paper', x0=0, x1=1, y0=expected, y1=expected, line=dict(color=COLORS[method], dash='dash', width=1.5)))
            notes.append(f'{name}: α = {fit.slope:.4f}; ориентир {expected:.4f}; точек n: {len(positive)}. Совпадение показателей само по себе не доказывает асимптотику.')
            for row in rows:
                if row['group'] in {g.identity for g in positive}:
                    row.update(alpha=fit.slope, regression_points=len(positive), theoretical_alpha=expected)
    elif graph == 'components':
        xlabel = 'Метод и конфигурация (n, k)'
        for group in groups:
            pairs = [o.metadata.get('stages', {}) for o in group.observations if o.record.status in SUCCESS]
            pairs = [p for p in pairs if p.get('diamond', {}).get('queries') is not None and p.get('herding', {}).get('queries') is not None and p.get('full', {}).get('queries') == p['diamond']['queries'] + p['herding']['queries']]
            if not pairs:
                continue
            method = group.method
            category = f"{METHOD_NAMES[method]}<br>n={group.configuration['n']}, k={group.configuration['k']}"
            for stage, label in (('diamond', 'Алмаз'), ('herding', 'Связывающий блок')):
                value = sum(p[stage]['queries'] for p in pairs)/len(pairs)
                traces.append(dict(type='bar', x=[category], y=[value], name=f'{METHOD_NAMES[method]} · {label}',
                                   legendgroup=method.value, marker=dict(color=COLORS[method], opacity=1 if stage == 'diamond' else .45,
                                   pattern=dict(shape='' if stage == 'diamond' else '/')), hovertemplate=f'{label}<br>Среднее Q: %{{y:.12g}}<br>Запусков: {len(pairs)}<extra></extra>'))
        notes.append('Столбцы содержат средние затраты двух этапов на одинаковом наборе успешных полных запусков; независимая проверка учитывается отдельно в JSON.')
    elif graph == 'dispersion':
        for values in series.values():
            method = values[0].method
            offset = {SearchMethod.CLASSICAL: -.22, SearchMethod.GROVER_FIXED: 0, SearchMethod.GROVER_BBHT: .22}[method]
            for group in values:
                observations = [(o, metric_value(o.record, result.options.effective_metric)) for o in group.observations]
                observations = [(o, v) for o, v in observations if v is not None]
                box = distribution != 'points' and len(observations) >= 2
                if box:
                    traces.append(dict(type='box', x=[group.x+offset]*len(observations), y=[v for o,v in observations],
                                       name=METHOD_NAMES[method], legendgroup=method.value, showlegend=False,
                                       marker=dict(color=COLORS[method]), line=dict(color=COLORS[method]),
                                       boxpoints=False, width=.18, quartilemethod='linear', hovertemplate='Медиана и межквартильный размах<br>Значение: %{y}<extra></extra>'))
                xs, ys, text, ids = [], [], [], []
                for item, value in observations:
                    fraction = int(hashlib.sha256(item.uid.encode()).hexdigest()[:8], 16)/0xffffffff-.5
                    xs.append(group.x+offset+fraction*.12);ys.append(value);ids.append(item.uid)
                    text.append(f"{METHOD_NAMES[method]}<br>n={item.record.n} · k={item.record.k} · s={item.record.sigma_bits}<br>seed={item.metadata.get('seed', 'не записан')} · испытание={item.metadata.get('trial', 'не записано')}<br>Q={metric_value(item.record, 'queries')} · значение={value}<br>Статус: {item.record.status}<br>Независимая проверка: {item.metadata.get('verified', 'не записана')}")
                traces.append(dict(type='scatter', mode='markers', x=xs, y=ys, text=text, customdata=ids,
                                   name=METHOD_NAMES[method], legendgroup=method.value, showlegend=group is values[0],
                                   marker=dict(color=COLORS[method], size=8, opacity=.66, symbol='circle', line=dict(width=.8, color='white')),
                                   hovertemplate='%{text}<extra></extra>'))
                traces.append(dict(type='scatter', mode='markers', x=[group.x+offset], y=[group.summary.median], name=METHOD_NAMES[method]+' · медиана',
                                   legendgroup=method.value, showlegend=False, marker=dict(color=COLORS[method], symbol='diamond', size=13, line=dict(color='white', width=2)),
                                   hovertemplate=f'Медиана успешных: %{{y:.12g}}<br>Запусков: {group.summary.count}<extra></extra>'))
        notes.append('Точки — реальные запуски, включая завершившиеся ошибкой с известными затратами; ромб — медиана успешных. Сдвиг по X только визуальный; точное n указано в подсказке и CSV. Коробка появляется от двух измерений; малая выборка не позволяет надёжно оценивать распределение.')
    else:
        for values in series.values():
            values = sorted(values, key=lambda g: g.x)
            method = values[0].method
            if graph in ('sigma', 'depth') and len({g.x for g in values}) < 2:
                notes.append('Для зависимости нужны хотя бы два различных значения параметра оси X при одинаковых остальных условиях.')
                continue
            metrics = [('Q', 'queries'), ('g', 'evaluations')] if graph == 'model_vs_actual' else [(None, None)]
            for label, metric in metrics:
                ys = [sum(v)/len(v) if (v := [metric_value(o.record, metric) for o in g.observations if o.record.status in SUCCESS and metric_value(o.record, metric) is not None]) else None for g in values] if metric else [g.value for g in values]
                name = METHOD_NAMES[method]+(f' · {label}' if label else '')
                traces.append(dict(type='scatter', mode='lines+markers', x=[g.x for g in values], y=ys,
                                   name=name, legendgroup=method.value, connectgaps=False,
                                   customdata=[g.identity for g in values], text=[_hover(g) for g in values],
                                   hovertemplate=name+'<br>%{text}<br>Значение: %{y:.12g}<extra></extra>',
                                   line=dict(color=COLORS[method], width=2.4, dash='dot' if label == 'g' else 'solid', shape='linear'),
                                   marker=dict(size=8, color=COLORS[method], symbol='circle')))
                if metric is None and result.options.uncertainty!='none':
                    up,down=[],[]
                    for g in values:
                        low,high=(g.ci_low,g.ci_high)
                        if result.options.uncertainty=='range':low,high=g.summary.minimum,g.summary.maximum
                        if result.options.uncertainty=='std' and g.summary.stddev is not None and g.value is not None:low,high=g.value-g.summary.stddev,g.value+g.summary.stddev
                        valid=low is not None and high is not None and g.value is not None
                        up.append(max(0,high-g.value) if valid else 0)
                        down.append(max(0,g.value-max(0,low)) if valid else 0)
                        if valid and low<0:notes.append('Нижняя граница интервала ограничена нулём; полные границы сохранены в CSV и JSON.')
                    traces[-1]['error_y']=dict(type='data',array=up,arrayminus=down,symmetric=False,visible=True,color=COLORS[method],thickness=1,width=3)
            if graph == 'depth':
                best = min((g for g in values if g.value is not None), key=lambda g: g.value, default=None)
                if best:traces.append(dict(type='scatter', mode='markers', x=[best.x], y=[best.value], name=METHOD_NAMES[method]+' · минимум среднего',
                                   legendgroup=method.value, marker=dict(color=COLORS[method], symbol='star', size=17), hovertemplate='Минимальное измеренное среднее: %{y:.12g}<extra></extra>'))
        if graph == 'model_vs_actual':
            ylabel = 'Запросы Q / вычисления g (разные метрики)'
            notes.append('Сплошная линия — модельные запросы Q, пунктир — реальные вычисления ГОСТ в классическом симуляторе. Их отношение не является ускорением программы.')
    if graph == 'speedup':
        shapes.append(dict(type='line', xref='paper', x0=0, x1=1, y0=1, y1=1, line=dict(color='#8795AA', width=1.5, dash='dash')))
        notes.append('Уровень 1 означает отсутствие преимущества по запросам; сравниваются средние только совместимых конфигураций.')
    seen_names=set()
    for trace in traces:
        if trace.get('showlegend',True):
            trace['showlegend']=trace.get('name') not in seen_names
            seen_names.add(trace.get('name'))
    values = [y for trace in traces for y in trace.get('y', []) if isinstance(y, (int, float)) and math.isfinite(y)]
    if graph=='components':
        totals=defaultdict(float)
        for trace in traces:
            for x,y in zip(trace['x'],trace['y']):totals[x]+=y
        values.extend(totals.values())
    positive = [v for v in values if v > 0]
    logarithmic = graph not in ('theory', 'components') and (scale == 'log' or scale == 'auto' and positive and max(positive)/min(positive) >= 20)
    zeros = values.count(0)
    for trace in traces:
        error=trace.get('error_y',{})
        for i,y in enumerate(trace.get('y',[])):
            if y is None or not error:continue
            upper=y+error['array'][i];lower=y-error['arrayminus'][i]
            values.append(upper)
            if logarithmic and lower<=0:
                error['arrayminus'][i]=0
                notes.append('Интервалы, пересекающие ноль, не изображаются вниз в логарифмическом масштабе; полные границы сохранены в CSV и JSON.')
            elif lower>0:values.append(lower)
    positive=[v for v in values if v>0]
    if logarithmic and zeros:
        notes.append(f'Нулевых измерений: {zeros}; они сохранены в CSV и доступны в линейном масштабе, логарифм нуля не определён.')
    if graph in ('theory','optimal'):
        yrange = [min(0, min(values, default=0)*1.2), max(1.1, max(values, default=0)*1.25)]
    elif logarithmic and positive:
        low, high = math.log10(min(positive)), math.log10(max(positive));pad=max(.18, (high-low)*.09)
        yrange = [low-pad, high+pad]
    else:
        yrange = [0, max(values, default=1)*1.13 or 1]
    background, foreground, grid = ('#121B2A', '#DBE5F5', '#2A374C') if dark else ('#F6FAFF', '#48668C', '#E1EBF7')
    layout = dict(paper_bgcolor=background, plot_bgcolor=background, font=dict(family='Segoe UI, Arial, sans-serif', size=13, color=foreground),
                  title=dict(text=title,x=.015,y=.97,xanchor='left',yanchor='top',font=dict(size=20,color='#1C3F70')),
                  margin=dict(l=62, r=24, t=66, b=54), hovermode='closest', dragmode='zoom', showlegend=True,
                  legend=dict(orientation='h', x=1, xanchor='right', y=1.115, yanchor='bottom', font=dict(size=12), groupclick='togglegroup', bgcolor='rgba(0,0,0,0)'),
                  xaxis=dict(title=dict(text=xlabel, font=dict(size=12)), gridcolor=grid, gridwidth=1,showgrid=True,zeroline=False, automargin=True, tickmode='auto' if graph in ('theory','optimal','components') else 'array', tickvals=sorted({g.x for g in groups}) if graph not in ('theory','optimal','components') else None),
                  yaxis=dict(title=dict(text=ylabel, font=dict(size=13)), gridcolor=grid, zeroline=False, type='log' if logarithmic else 'linear', range=yrange, automargin=True),
                  shapes=shapes, barmode='stack' if graph == 'components' else 'group',bargap=.32, hoverlabel=dict(bgcolor='#FFFFFF',bordercolor='#C3D8F1',font=dict(size=13,color='#244A79')),
                  uirevision=canonical((graph,result.options.stage,result.options.filters,scale)), transition=dict(duration=0))
    if focus:
        for trace in traces:
            trace['opacity'] = 1 if trace.get('legendgroup') == focus else .2
    if logarithmic and positive:
        ticks=[factor*10**power for power in range(math.floor(yrange[0]),math.ceil(yrange[1])+1) for factor in (1,2,5) if 10**yrange[0]<=factor*10**power<=10**yrange[1]]
        def label(value):
            divisor,suffix=(1e9,' млрд') if value>=1e9 else (1e6,' млн') if value>=1e6 else (1e3,' тыс.') if value>=1e3 else (1,'')
            return f'{value/divisor:g}'.replace('.',',')+suffix
        layout['yaxis'].update(tickmode='array',tickvals=ticks,ticktext=[label(value) for value in ticks])
    empty = not any(any(y is not None for y in t.get('y', [])) for t in traces)
    if empty:
        layout['annotations'] = [dict(text='Недостаточно данных', x=.5, y=.5, yshift=20, xref='paper', yref='paper', showarrow=False, font=dict(size=23, color=foreground)),
                                 dict(text='Выберите другую серию или дождитесь новых результатов', x=.5, y=.5, yshift=-16, xref='paper', yref='paper', showarrow=False, font=dict(size=13, color='#8795AA'))]
        layout['xaxis']['visible'] = layout['yaxis']['visible'] = False
    known = sum(o.record.status in SUCCESS for o in result.observations)
    total = len(result.observations)
    notes.insert(0, f'Успешных запусков: {known} из {total}; остальные сохранены в статистике. Числовые средние рассчитаны по успешным запускам с известными затратами.')
    if not notes[1:] and traces:
        notes.append(f'Показано {len(groups)} измеренных групп при фиксированных остальных параметрах; экспериментальные точки соединены прямыми отрезками.')
    notes.extend(result.notices if graph != 'theory' else [n for n in result.notices if 'симулятора' in n])
    insight=notes[1] if len(notes)>1 else ''
    if not empty and graph in ('queries_n','evaluations_n','runtime_n'):
        insight=f"Измеренных конфигураций: {len(groups)}; успешных запусков: {known}/{total}. Показаны только реальные измерения при фиксированных остальных параметрах."
    return dict(data=traces, layout=layout, title=title, subtitle=STAGES.get(result.options.stage, ''), empty=empty, insight=insight,
                conclusion=' '.join(dict.fromkeys(notes)), rows=rows, options=asdict(result.options), scale='log' if logarithmic else 'linear',
                sources=sorted({uid for group in result.groups for uid in group.source_ids}))


def write_chart(path, spec, entries=(), dpi=300):
    """Экспортирует те же числовые серии в печатный рисунок или таблицу с происхождением."""
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.json':
        origins = [dict(id=e.identity, source=e.source, source_sha256=e.source_digest, metadata=e.metadata) for e in entries if e.identity in spec['sources']]
        path.write_text(json.dumps(spec | {'provenance': origins}, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        return
    if path.suffix == '.csv':
        keys = list(dict.fromkeys(key for row in spec['rows'] for key in row))
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=keys or ['id','Q']);writer.writeheader();writer.writerows(spec['rows'])
        return
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.ticker import MaxNLocator
    import matplotlib
    with matplotlib.rc_context({'font.family':'DejaVu Sans','font.weight':'normal','svg.fonttype':'none'}):
        figure = Figure(figsize=(11.7, 6.6), facecolor='white');FigureCanvasAgg(figure)
        ax = figure.add_subplot();ax.set_facecolor('white');labels=set();bottoms={}
        categories=list(dict.fromkeys(str(x).replace('<br>','\n') for trace in spec['data'] if trace['type']=='bar' for x in trace['x']))
        bar_counts={category:sum(str(x).replace('<br>','\n')==category for trace in spec['data'] if trace['type']=='bar' for x in trace['x']) for category in categories}
        bar_used=defaultdict(int)
        for trace in spec['data']:
            x, y = trace.get('x', []), trace.get('y', [])
            x=[value.replace('<br>','\n') if isinstance(value,str) else value for value in x]
            color=trace.get('line',{}).get('color', trace.get('marker',{}).get('color','#2464FF'))
            name=trace.get('name','');label=name if name not in labels and trace.get('showlegend',True) else '_nolegend_';labels.add(name)
            if trace['type']=='bar':
                bottom=[bottoms.get(str(v),0) for v in x] if spec['options']['graph']=='components' else None
                positions=[];widths=[]
                for category in x:
                    category=str(category);count=1 if bottom is not None else bar_counts[category]
                    positions.append(categories.index(category)+(0 if bottom is not None else (bar_used[category]-(count-1)/2)*.7/count))
                    widths.append(.7/count);bar_used[category]+=1
                ax.bar(positions,y,width=widths,bottom=bottom,color=color,alpha=trace.get('marker',{}).get('opacity',1),label=label,hatch='//' if trace.get('marker',{}).get('pattern',{}).get('shape') else None)
                for xx,yy in zip(x,y):bottoms[str(xx)]=bottoms.get(str(xx),0)+(yy or 0)
            elif trace['type']=='box':
                if x and y:ax.boxplot(y, positions=[x[0]], widths=.18, manage_ticks=False, showfliers=True)
            else:
                ax.plot(x,[float('nan') if v is None else v for v in y],color=color,marker='o',markersize=4,linewidth=1.6,
                        linestyle=':' if trace.get('line',{}).get('dash')=='dot' else '-' if 'lines' in trace.get('mode','') else 'None',alpha=trace.get('marker',{}).get('opacity',1),label=label)
                error=trace.get('error_y')
                if error:ax.errorbar(x,[float('nan') if v is None else v for v in y],yerr=[error['arrayminus'],error['array']],fmt='none',ecolor=color,elinewidth=.8,capsize=2)
        for shape in spec['layout'].get('shapes',[]):
            ax.axhline(shape['y0'],color=shape['line']['color'],linestyle='--',linewidth=1)
        if categories:ax.set_xticks(range(len(categories)),categories)
        ax.set_title(spec['title']+'\n'+spec['subtitle'],loc='left',fontsize=16,pad=22)
        ax.set_xlabel(spec['layout']['xaxis']['title']['text']);ax.set_ylabel(spec['layout']['yaxis']['title']['text'])
        if spec['scale']=='log':ax.set_yscale('log');ax.set_ylim(*(10**v for v in spec['layout']['yaxis']['range']))
        else:ax.set_ylim(*spec['layout']['yaxis']['range'])
        if spec['options']['graph'] not in ('theory','optimal','components'):ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        for spine in ('top','right'):ax.spines[spine].set_visible(False)
        ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
        if ax.get_legend_handles_labels()[0]:ax.legend(loc='upper center',bbox_to_anchor=(.5,-.17),ncol=3,frameon=False,fontsize=9)
        if spec['empty']:ax.text(.5,.5,'Недостаточно данных',transform=ax.transAxes,ha='center',fontsize=20)
        figure.subplots_adjust(left=.1,right=.97,top=.83,bottom=.25)
        figure.savefig(path,dpi=dpi,format=path.suffix[1:]);figure.clear()
        if path.suffix=='.svg':path.write_text('\n'.join(line.rstrip() for line in path.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')


def export_thesis(engine, options, output):
    """Сохраняет двенадцать научных представлений и явные причины недоступности данных."""
    output = Path(output);output.mkdir(parents=True, exist_ok=True)
    manifest = dict(created_at=datetime.now(timezone.utc).isoformat(), charts=[], unavailable=[], scope='Одна выбранная совместимая серия на график; параметры зафиксированы в JSON.')
    for identity, graph, stage in THESIS_GRAPHS:
        selected = options_for(options, graph, stage)
        cohort = engine.suggested_cohort(selected)
        if cohort:
            from .comparison_analysis import field_value
            selected=replace(selected,filters=selected.filters+tuple((k,canonical(field_value(cohort,k))) for k in ('n','k','s') if (k != axis_for(graph) or graph=='components') and not (k=='k' and graph=='optimal')))
        result = engine.analyze(selected)
        spec = chart_spec(result)
        if spec['empty']:
            manifest['unavailable'].append(dict(id=identity,title=spec['title'],reason=spec['conclusion']))
            write_chart(output/(identity+'.json'),spec,engine.entries.values())
            continue
        files=[]
        for ext in ('png','svg','csv','json'):
            path=output/(identity+'.'+ext);write_chart(path,spec,engine.entries.values())
            files.append(dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        manifest['charts'].append(dict(id=identity,title=spec['title'],files=files))
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest
