import datetime as dt
from fastapi.testclient import TestClient
import importlib
api_module = importlib.import_module("app.api.app")
from app.data.repositories.json_repos import json_repositories_in_memory
from tests.factories import make_repos


def test_health_endpoint():
    client=TestClient(api_module.app)
    r=client.get('/api/health')
    assert r.status_code==200
    assert r.json()['status']=='ok'


def test_api_generate_uses_planner(monkeypatch):
    repos=make_repos()
    monkeypatch.setattr(api_module,'build_planner',lambda: __import__('app.services.planner',fromlist=['PlannerService']).PlannerService(repos))
    client=TestClient(api_module.app)
    start=(dt.date.today()+dt.timedelta(days=30)).isoformat()
    end=(dt.date.today()+dt.timedelta(days=31)).isoformat()
    body={'trip':{'destination':'Testville','start_date':start,'end_date':end,'travellers':2,'trip_type':'friends','budget':30000,'interests':['beach']}}
    r=client.post('/api/plans/generate',json=body)
    assert r.status_code==200
    assert r.json()['destination_id']=='testville'


def test_api_validation_endpoint(monkeypatch):
    repos=make_repos()
    monkeypatch.setattr(api_module,'build_planner',lambda: __import__('app.services.planner',fromlist=['PlannerService']).PlannerService(repos))
    client=TestClient(api_module.app)
    start=dt.date.today()+dt.timedelta(days=30); end=start+dt.timedelta(days=1)
    body={'trip':{'destination':'Testville','start_date':start.isoformat(),'end_date':end.isoformat(),'travellers':2,'trip_type':'friends','budget':30000},'itinerary':{'plan_id':'p','days':[{'day':1,'date':start.isoformat(),'items':[]},{'day':2,'date':end.isoformat(),'items':[]}]},'modifications':[{'action':'reoptimize'}]}
    r=client.post('/api/plans/validate',json=body)
    assert r.status_code==200
    assert r.json()['feasible'] is True
