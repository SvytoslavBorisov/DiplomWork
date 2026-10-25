"""Проверяет автономную поставку в отдельной базе без изменения пользовательских экспериментов."""

from collections import Counter
import json
import os
from pathlib import Path
import sys
import traceback


def run(output):
    output.mkdir(parents=True,exist_ok=True)
    portable='--portable-storage' in sys.argv
    if portable:os.environ.pop('HERDINGLAB_DATA_DIR',None)
    else:os.environ['HERDINGLAB_DATA_DIR']=str(output/'personal')
    os.environ['OPENBLAS_NUM_THREADS']='1'
    from PySide6.QtCore import QTimer,Qt,QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from main import create_application
    from .experiment_store import ExperimentStore,EXAMPLES_PATH
    from .backend_adapter import BackendAdapter,BuildRequest,AttackRunResult
    from .experiment_controller import ExperimentController
    from .experiment_replay import prepare_replay
    from .project_paths import DATA_ROOT,new_diamond_directory,new_experiment_directory
    from .frozen_runtime import close_startup_splash
    from .scientific_charts import chart_spec
    from .comparison_analysis import AnalysisOptions,canonical
    from ui.log_translation import translate_log
    from CppCore import cpp_core_available
    report={'frozen':getattr(sys,'frozen',False),'errors':[],'builds':[],'attacks':[]}
    def fail(message,trace=''):
        report['errors'].append(str(message)+'\n'+trace);finish()
    app,window=create_application([]);window.resize(1366,768);window.show();close_startup_splash();tab=window.comparison_tab
    chart=tab.scientific_chart;store=ExperimentStore();report['entries']=len(store.entries)
    original_entries=len(store.entries)
    if portable:
        expected=Path(sys.executable).parent
        assert store.local_path==expected/'experiments.json'
        assert DATA_ROOT==expected and new_diamond_directory().is_relative_to(expected) and new_experiment_directory('check').is_relative_to(expected)
        report['portable_database']=str(store.local_path)
    full=[e for e in store.entries if e.record.experiment_type=='full'];counts=Counter((e.record.n,e.record.k,e.record.method) for e in full)
    report['seed_groups']=len(counts);report['seed_exactly_three']=bool(counts) and set(counts.values())=={3} and all(e.record.sigma_bits==4 for e in full)
    report['native_core']=cpp_core_available()
    report['graphs']=[tab.graph_kind.itemData(i) for i in range(tab.graph_kind.count())]
    report['log_example']=translate_log('[Blackburn] Граф: |E|=8, matching=4/4, L=8, вычислений=64.')
    report['button_heights']=[window.diamond_tab.parameters.build_button.height(),window.diamond_tab.results.verify_button.height()]
    window.grab().save(str(output/'diamond.png'))
    tab.select_record(next(e.record for e in store.entries if e.record.experiment_type=='diamond'))
    report['before_first_open']=tab.stage_filter.currentData()
    window.header.tabs.setCurrentIndex(2)
    report['defaults']=dict(stage=tab.stage_filter.currentData(),**{k:c.currentData() for k,c in tab.value_filters.items()})
    window.grab().save(str(output/'loading.png'))
    state={'started':False,'index':0};controller=ExperimentController(BackendAdapter(),window)
    def render_ready():
        if not chart._first_render or state['started']:return
        state['started']=True;QTimer.singleShot(200,inspect)
    def inspect():
        try:
            replay=[]
            for stage in ('diamond','herding','full'):
                for method in ('classical','grover_fixed','grover_bbht'):
                    entry=next(e for e in store.entries if e.record.n==12 and e.record.k==3 and e.record.method==method and e.record.experiment_type==stage)
                    plan=prepare_replay(entry,store,BackendAdapter())
                    assert bool(plan.request)==(stage!='herding') and bool(plan.attack)==(stage!='diamond')
                    replay.append(dict(stage=stage,method=method))
            report['seed_replay_plans']=replay
            window.grab().save(str(output/'comparison.png'))
            report['loading_hidden']=chart._loading.isHidden();report['chart_error']=chart.error
            tab.graph_kind.showPopup();app.processEvents()
            tab.graph_kind.view().window().grab().save(str(output/'dropdown.png'))
            report['dropdown_font']=dict(family=tab.graph_kind.view().font().family(),bold=tab.graph_kind.view().font().bold(),open_chevron=tab.graph_kind._popup_open)
            tab.graph_kind.hidePopup();report['chevron_closed']=not tab.graph_kind._popup_open
            check_js="JSON.stringify({width:el._fullLayout.width,height:el._fullLayout.height,bodyWidth:document.body.clientWidth,bodyHeight:document.body.clientHeight,visible:getComputedStyle(el).visibility})"
            chart.web.page().runJavaScript(check_js,lambda value:report.update(chart_size=json.loads(value)))
            removed={'runtime_n','optimal','sigma','theory'};assert not removed.intersection(report['graphs'])
            assert report['defaults']==dict(stage='full',n=None,k=canonical(4),s=canonical(4)),report['defaults']
            continuity={}
            for kind in ('queries_n','evaluations_n','model_vs_actual','speedup'):
                from dataclasses import replace
                result=tab.analysis.analyze(replace(tab._options(),graph=kind,presentation='speedup' if kind=='speedup' else 'complexity'))
                spec=chart_spec(result);continuity[kind]={method:any(16 in t.get('x',[]) and 20 in t.get('x',[]) for t in spec['data'] if t.get('legendgroup')==method and 'lines' in t.get('mode','')) for method in ('grover_fixed','grover_bbht')}
            report['continuity']=continuity;assert all(all(v.values()) for v in continuity.values())
            tab.point_inspector.present('Информация о точке','Q',{'Значение':'123'});QTest.mouseClick(window.header,Qt.MouseButton.LeftButton,pos=QPoint(10,10));report['point_outside_closed']=not tab.point_inspector.isVisible()
            inspector=window.diamond_tab.view.inspector;window.header.tabs.setCurrentIndex(0);inspector.present('Вершина','h',{'Хэш-код':'abc'});QTest.mouseClick(window.header,Qt.MouseButton.LeftButton,pos=QPoint(10,10));report['vertex_outside_closed']=not inspector.isVisible()
            window.header.tabs.setCurrentIndex(2);tab.graph_kind.setCurrentIndex(tab.graph_kind.findData('components'))
            report['components_stage_hidden']=tab.stage_filter.isHidden();report['components_no_s']=all('s=' not in str(t.get('x')) for t in tab._chart_spec['data'])
            tab.graph_kind.setCurrentIndex(0);build_next()
        except Exception as exc:fail(str(exc),traceback.format_exc())
    def build_next():
        if state['index']==3:
            report['cancel_requested']=True
            controller.build_finished.disconnect(built);controller.build_cancelled.connect(cancelled)
            controller.start_build(BuildRequest('classical',8,28,1,12,100000000,output/'cancel',sigma_bits=4,seed=7,threads=1))
            QTimer.singleShot(150,controller.cancel_build);return
        method=('classical','grover_fixed','grover_bbht')[state['index']];state['method']=method
        directory=new_diamond_directory() if portable else output/method
        controller.start_build(BuildRequest(method,2,8,1,12,1000000,directory,sigma_bits=4,seed=20261025,threads=1))
    def built(result):
        try:
            if isinstance(result,AttackRunResult):
                store.add_attack(state['build'].data,result.result,result.elapsed_seconds,state['build'].path,1000000)
                store.add_full(state['build'],result,1000000)
                report['attacks'].append(dict(method=state['method'],verified=result.result.root==result.result.verified_root and result.result.root_sigma==result.result.verified_sigma));state['index']+=1;build_next();return
            state['build']=result
            adapter=BackendAdapter();assert adapter.load_json(result.path)==result.data
            entry=store.add_completed(result.data,result.elapsed_seconds,result.path)
            assert len(entry.metadata.get('code_sha256',''))==64
            report['builds'].append(dict(method=state['method'],path=str(result.path),builder=result.data.get('builder'),vertices=sum(len(x) for x in result.data['structure'])))
            if state['method']=='classical':assert 'builder' not in result.data
            controller._launch_process(dict(operation='attack',data=result.data,description='Проверка',event_result='Проверка',method=state['method'],trials_limit=1000000,seed=20261025,threads=1))
        except Exception as exc:fail(str(exc),traceback.format_exc())
    def cancelled():
        report['cancelled']=True
        try:
            for extension in ('csv','png','svg','json'):tab.export_to(output/('chart.'+extension))
            report['export']=True
            loaded=ExperimentStore(None,store.local_path)
            assert len(loaded.entries)==9 and len(store.entries)==original_entries+9
            report['persisted_entries']=len(loaded.entries)
            report['roundtrip_json']=True
        except Exception as exc:report['errors'].append(str(exc))
        finish()
    def finish():
        (output/'smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');window.close();QTimer.singleShot(300,app.quit)
    chart.rendered.connect(render_ready);controller.build_finished.connect(built);controller.build_failed.connect(fail)
    QTimer.singleShot(100,render_ready);QTimer.singleShot(90000,lambda:fail('Истекло время проверки сборки'))
    app.exec()
    return 0 if not report['errors'] and report.get('cancelled') and len(report['attacks'])==3 else 1
