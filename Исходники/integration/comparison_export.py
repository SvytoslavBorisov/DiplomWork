"""Рисует и экспортирует научные графики по готовым агрегатам без вычислений криптографии."""

from collections import defaultdict
import csv
import math
from pathlib import Path
import re
import textwrap

import matplotlib
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, ScalarFormatter

from algorithms.search_methods import SearchMethod
from .comparison_analysis import GRAPH_TITLES, METRIC_UNITS, METHOD_NAMES, STAGES, AnalysisResult, canonical


COLORS={SearchMethod.CLASSICAL:"#2464FF",SearchMethod.GROVER_FIXED:"#934EFF",SearchMethod.GROVER_BBHT:"#00AB73"}
MARKERS={SearchMethod.CLASSICAL:"o",SearchMethod.GROVER_FIXED:"s",SearchMethod.GROVER_BBHT:"^"}


def layout_compact_figure(figure):
    """Размещает оси и нижнюю строку легенды с учётом фактического размера графика."""
    if not getattr(figure,"_comparison_compact",False) or not figure.axes:return
    ax=figure.axes[0]
    width,height=figure.get_size_inches()*72
    legend=ax.get_legend()
    rows=getattr(figure,"_comparison_legend_rows",1)
    bottom=min(42+13*(rows-1),height*.32)
    top=min(29,height*.18)
    left=min(48,width*.16);right=12
    figure.subplots_adjust(left=left/width,right=1-right/width,top=1-top/height,bottom=bottom/height)
    ax.xaxis.set_label_coords(0,-(bottom-10)/(height-top-bottom))
    ax.xaxis.label.set_horizontalalignment("left")
    ax.xaxis.label.set_verticalalignment("center")
    if legend:legend.set_bbox_to_anchor((1-right/width,(10+6.5*(rows-1))/height),transform=figure.transFigure)


def title(result):
    if result.options.presentation=="speedup":return GRAPH_TITLES["speedup"]
    if result.options.presentation=="dispersion":return "Распределение результатов: "+METRIC_UNITS[result.options.effective_metric]
    return GRAPH_TITLES[result.options.graph]


def parameter_caption(result):
    configs=[group.configuration for group in result.plotted]
    parts=[STAGES.get(result.options.stage,"Этапы показаны раздельно")]
    for key in ("n","k","s","N","rounds","prefix_blocks","version","scenario"):
        if key==result.options.effective_axis:continue
        values={canonical(config.get(key)) for config in configs}
        if len(values)==1:
            value=configs[0].get(key)
            label={"rounds":"раундов","prefix_blocks":"блоков префикса","version":"версия","scenario":"серия"}.get(key,key)
            parts.append(f"{label} = {'не записано' if value is None else value}")
        elif len(values)>1:parts.append(f"{key}: раздельные конфигурации")
    return " · ".join(parts)


def point_description(group, result):
    config=group.configuration
    summary=group.summary
    lines=[f"{METHOD_NAMES[group.method]} · {result.options.effective_axis} = {group.x}",
           f"n={config['n']} · k={config['k']} · s={config['s']} · N={config['N']}",
           f"Листьев: {2**config['k']} · раундов: {config['rounds']} · блоков префикса: {config['prefix_blocks']}",
           f"Измерений: {summary.count}; успешно: {group.successful}/{group.total}; ошибок: {group.failed}; прервано: {group.interrupted}; пропущено: {group.skipped}",
           f"Среднее: {number(summary.mean)}; медиана: {number(summary.median)}; σ: {number(summary.stddev)}"]
    if group.ci_low is not None:lines.append(f"95% ДИ: [{number(group.ci_low)}; {number(group.ci_high)}]")
    if group.baseline is not None:lines.append(f"Запросное квантовое ускорение: {number(group.value)} раз; классическая база: {number(group.baseline_mean)} ({group.baseline_count})")
    lines.append(f"Версия: {config['version']} · {config['scenario']}")
    lines.append("Настройки: "+canonical(group.profile))
    return "\n".join(lines)


def number(value):
    if value is None:return "–"
    return f"{value:.5g}".replace(".",",")


def render_figure(figure: Figure, result: AnalysisResult, selected=(), compact=False):
    figure.clear()
    figure._comparison_compact=compact
    figure.set_facecolor("white")
    ax=figure.add_subplot(111)
    mapping={}
    options=result.options
    groups=result.plotted
    with matplotlib.rc_context({"font.family":"DejaVu Sans","mathtext.fontset":"stix"}):
        seen=set()
        series=defaultdict(list)
        for group in groups:series[group.series_key].append(group)
        for key,members in series.items():
            members=sorted(members,key=lambda group:group.x)
            method=members[0].method;color=COLORS[method]
            label=METHOD_NAMES[method] if method not in seen else "_nolegend_"
            if options.graph=="theory" and label!="_nolegend_":label+=" · измерения"
            seen.add(method)
            xs=[group.x for group in members];ys=[group.value for group in members]
            if options.presentation=="dispersion":
                for group in members:
                    values=[value for value in group.values if not options.logarithmic or value>0]
                    if not values:continue
                    offset={SearchMethod.CLASSICAL:-.18,SearchMethod.GROVER_FIXED:0,SearchMethod.GROVER_BBHT:.18}[method]
                    if len(values)>1 and len(values)==len(group.values):
                        box=ax.boxplot([values],positions=[group.x+offset],widths=.15,manage_ticks=False,patch_artist=True,
                                       showfliers=True,boxprops=dict(facecolor=color,edgecolor=color,alpha=.28),
                                       medianprops=dict(color=color,linewidth=2),whiskerprops=dict(color=color),capprops=dict(color=color))
                    elif len(values)!=len(group.values):
                        ax.scatter([group.x+offset]*len(values),values,color=color,s=10,alpha=.4)
                    dot=ax.scatter([group.x+offset],[group.summary.median],color=color,marker=MARKERS[method],s=36,label=label,picker=7)
                    mapping[dot]=[group];label="_nolegend_"
            else:
                positions={group.x for group in result.groups if group.series_key==key}
                if options.presentation=="speedup":positions.update(group.x for group in result.basis if key.startswith(group.series_key))
                line_x=sorted(positions);point_values={group.x:group.value for group in members}
                ax.plot(line_x,[point_values.get(x,math.nan) for x in line_x],color=color,linewidth=1.9,label=label,solid_capstyle="round")
                scatter=ax.scatter(xs,ys,color=color,marker=MARKERS[method],s=43,edgecolors="white",linewidths=.9,zorder=4,picker=7)
                mapping[scatter]=members
                intervals={}
                for group in members:
                    low=high=None
                    if options.uncertainty=="ci":low,high=group.ci_low,group.ci_high
                    elif options.uncertainty=="std" and group.summary.stddev is not None and not group.baseline:
                        deviation=group.summary.stddev/(group.theory if options.theory_ratio else 1)
                        low,high=group.value-deviation,group.value+deviation
                    elif options.uncertainty=="range" and not group.baseline:
                        divisor=group.theory if options.theory_ratio else 1
                        low,high=group.summary.minimum/divisor,group.summary.maximum/divisor
                    if low is not None and high is not None and low<=group.value<=high and (not options.logarithmic or low>0):
                        intervals[group.x]=(low,high)
                        ax.errorbar(group.x,group.value,yerr=[[group.value-low],[high-group.value]],fmt="none",capsize=3,elinewidth=1,color=color,alpha=.5,zorder=3)
                if len(intervals)>1:
                    ax.fill_between(line_x,[intervals.get(x,(math.nan,math.nan))[0] for x in line_x],
                                    [intervals.get(x,(math.nan,math.nan))[1] for x in line_x],color=color,alpha=.075,linewidth=0,zorder=2)
                if options.effective_metric=="runtime" and options.aggregation=="mean" and options.presentation!="speedup":
                    medians=[group.summary.median for group in members]
                    ax.scatter(xs,medians,marker="x",color=color,s=30,zorder=5,label="Медиана времени" if "median" not in seen else "_nolegend_")
                    seen.add("median")
                if options.graph=="theory":
                    theoretical=[group for group in members if group.theory is not None]
                    if theoretical and not options.theory_ratio:
                        ax.plot([group.x for group in theoretical],[group.theory for group in theoretical],"--",color=color,linewidth=1.3,
                                label=METHOD_NAMES[method]+" · асимптотическая форма" if ("theory",method) not in seen else "_nolegend_")
                        seen.add(("theory",method))
            highlighted=[group for group in members if group.identity in selected]
            if highlighted:
                ax.scatter([group.x for group in highlighted],[group.summary.median if options.presentation=="dispersion" else group.value for group in highlighted],
                           s=115,facecolors="none",edgecolors="#12213B",linewidths=1.4,zorder=7)
        if options.presentation=="speedup":
            ax.axhline(1,color="#71819B",linestyle="--",linewidth=1,label="S = 1: без преимущества")
            ylabel="Запросное квантовое ускорение S, раз"
        elif options.graph=="theory" and options.theory_ratio:
            ylabel="Q / асимптотическая форма, усл. ед."
        else:ylabel=METRIC_UNITS[options.effective_metric]
        ax.set_ylabel(ylabel,fontsize=10)
        axis=options.effective_axis
        ax.set_xlabel(f"${axis}$"+(", бит" if axis in ("n","s") else " — глубина алмазной структуры"),fontsize=11)
        if axis=="n" and result.groups:ax.set_xticks(sorted({group.x for group in result.groups}))
        else:ax.xaxis.set_major_locator(MaxNLocator(integer=True,nbins=9,min_n_ticks=1))
        if options.logarithmic:ax.set_yscale("log")
        else:
            formatter=ScalarFormatter(useMathText=True);formatter.set_powerlimits((-3,4));ax.yaxis.set_major_formatter(formatter)
        if not groups:
            message=result.notices[0] if options.presentation=="speedup" and result.notices else "Нет измерений для выбранных фильтров"
            ax.text(.5,.5,"\n".join(textwrap.wrap(message,70)),ha="center",va="center",transform=ax.transAxes,color="#71819B",fontsize=11)
        if groups:
            handles,labels=ax.get_legend_handles_labels()
            if handles:
                keys=[];captions=[]
                for handle,label in zip(handles,labels):
                    if compact and " · асимптотическая форма" in label:
                        label="Асимптотическая форма"
                        if label in captions:continue
                        handle=Line2D([],[],linestyle="--",linewidth=1.3,color="#71819B")
                    elif compact and label.removesuffix(" · измерения") in METHOD_NAMES.values():
                        label=label.removesuffix(" · измерения")
                        method=next(method for method,name in METHOD_NAMES.items() if name==label)
                        handle=Line2D([],[],linestyle="none",marker="o",markersize=6,color=COLORS[method])
                    elif isinstance(handle,Line2D) and handle.get_linestyle()=="-":
                        handle=Line2D([],[],linestyle="none",marker="o",markersize=6,color=handle.get_color())
                    keys.append(handle);captions.append(label)
                columns=2 if len(keys)==4 else min(3,len(keys));figure._comparison_legend_rows=math.ceil(len(keys)/columns)
                ax.legend(keys,captions,fontsize=8.5,loc="center right" if compact else "best",frameon=False,
                          ncol=columns if compact else 1,handlelength=1.2,handletextpad=.45,columnspacing=1.6,
                          borderaxespad=0,labelcolor="#34445F")
        else:figure._comparison_legend_rows=1
        ax.set_facecolor("#FDFEFF")
        ax.grid(True,color="#E4EBF5",linewidth=.65);ax.set_axisbelow(True)
        if options.logarithmic:ax.grid(True,which="minor",axis="y",color="#EDF2F9",linewidth=.4,alpha=.65)
        ax.margins(x=.035,y=.12)
        ax.spines[["top","right"]].set_visible(False)
        for side in ("bottom","left"):
            ax.spines[side].set_color("#BECDE0");ax.spines[side].set_linewidth(.7)
        ax.tick_params(colors="#657A99",labelsize=9,length=3,pad=5)
        ax.tick_params(which="minor",length=0)
        ax.set_title("\n".join(textwrap.wrap(title(result),85)),fontsize=11,pad=12,color="#34445F")
        caption=parameter_caption(result)
        warning=""
        if options.presentation=="speedup":warning="Отношение средних Q; интервалы — приближение для независимых средних."
        elif options.graph=="theory":warning="Пунктир — асимптотическая форма, не точное предсказание числа запросов."
        elif options.effective_metric=="runtime":warning="Квантовые методы: время классического симулятора."
        else:warning="Статистика условна по успешным запускам; Q — запросная модель."
        if options.logarithmic and any(group.value is not None and group.value<=0 for group in result.groups):warning+=" Нули скрыты в логарифмической шкале."
        if options.logarithmic and options.uncertainty=="ci" and any(group.ci_low is not None and group.ci_low<=0 for group in groups):warning+=" ДИ через 0: границы в CSV."
        footer="\n".join(textwrap.wrap(caption,120))+"\n"+warning
        if not compact:
            figure.text(.5,.015,footer,ha="center",va="bottom",fontsize=8,color="#526581",fontfamily="DejaVu Sans")
        if compact:layout_compact_figure(figure)
        else:figure.subplots_adjust(left=.10,right=.98,top=.90,bottom=min(.28,.13+.023*len(footer.splitlines())))
        for artist in [ax.title,ax.xaxis.label,ax.yaxis.label,*ax.get_xticklabels(),*ax.get_yticklabels()]:artist.set_fontfamily("DejaVu Sans")
    return ax,mapping


def export_csv(path, result):
    fields=("graph","presentation","method","axis","x","scale","uncertainty","metric","statistic_metric","value","aggregation","count","successful","failed","interrupted","skipped","missing","success_rate",
            "mean","median","minimum","maximum","stddev","ci95_low","ci95_high","ci_target","baseline_mean","baseline_count","theory_order","theory_note","raw_values","plotted_values","configuration","method_profile","measurement_version","source_ids")
    with Path(path).open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for group in result.plotted:
            summary=group.summary
            writer.writerow(dict(graph=title(result),presentation=result.options.presentation,method=METHOD_NAMES[group.method],axis=result.options.effective_axis,x=group.x,
                                 scale="log" if result.options.logarithmic else "linear",uncertainty=result.options.uncertainty,
                                 metric="query_speedup" if group.baseline else "experiment_over_theory" if result.options.theory_ratio else result.options.effective_metric,
                                 statistic_metric=result.options.effective_metric,value=group.summary.median if result.options.presentation=="dispersion" else group.value,
                                 aggregation="median" if result.options.presentation=="dispersion" else "ratio_of_means" if group.baseline else result.options.aggregation,
                                 count=summary.count,successful=group.successful,failed=group.failed,interrupted=group.interrupted,skipped=group.skipped,missing=group.missing,
                                 success_rate=group.success_rate,mean=summary.mean,median=summary.median,minimum=summary.minimum,maximum=summary.maximum,stddev=summary.stddev,
                                 ci95_low=group.ci_low,ci95_high=group.ci_high,ci_target="ratio_of_independent_means" if group.baseline else "mean" if group.ci_low is not None else "",
                                 baseline_mean=group.baseline_mean,baseline_count=group.baseline_count,
                                 theory_order=group.theory,theory_note=group.theory_note,raw_values=canonical(group.values),
                                 plotted_values=canonical(tuple(value for value in group.values if not result.options.logarithmic or value>0)),
                                 configuration=canonical(group.configuration),method_profile=canonical(group.profile),
                                 measurement_version=group.configuration["version"],source_ids=canonical(group.source_ids)))


def suggested_filename(result):
    name=f"{result.options.graph}_{result.options.presentation}_{result.options.stage or 'stages'}_{result.options.effective_metric}_{'log' if result.options.logarithmic else 'linear'}"
    for key in ("n","k","s","N"):
        values={group.configuration.get(key) for group in result.plotted}
        if len(values)==1:name+=f"_{key}{next(iter(values))}"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]',"_",name)


def export_figure(path, result, dpi=300):
    path=Path(path)
    if path.suffix.lower() not in (".png",".svg"):raise ValueError("Поддерживаются SVG и PNG.")
    if dpi<300:raise ValueError("Экспорт PNG требует не менее 300 DPI.")
    figure=Figure(figsize=(9.4,5.8),dpi=dpi)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    FigureCanvasAgg(figure)
    render_figure(figure,result)
    metadata={"Title":title(result),"Description":parameter_caption(result)}
    if path.suffix.lower()==".svg":metadata["Date"]=None
    with matplotlib.rc_context({"svg.fonttype":"path","svg.hashsalt":"kvantalmaz-scientific-comparison"}):
        figure.savefig(path,dpi=dpi,facecolor="white",bbox_inches="tight",metadata=metadata)
    if path.suffix.lower()==".svg":
        path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf8").splitlines())+"\n",encoding="utf8",newline="\n")
    figure.clear()
