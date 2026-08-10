import statistics
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from polyglot.interfaces.http.routes.word_bank import SqlWordBankService
from polyglot.modules.lexicon.core.fixtures import (
    load_word_bank_fixture,
    materialize_word_bank_fixture,
)

from .test_ingestion_postgres import seed_profiles, uid

ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "canonical" / "FX-WB"


async def test_fx_wb_loads_real_100k_and_meets_bounded_sql_p95(migration_session) -> None:
    await seed_profiles(migration_session)
    fixture = load_word_bank_fixture(ROOT)
    loaded = await materialize_word_bank_fixture(
        migration_session, fixture=fixture, profile_id=uid(11)
    )
    await migration_session.commit()

    counts = (
        await migration_session.execute(
            text(
                "SELECT (SELECT count(*) FROM lexicon.lexical_reference_entries),"
                "(SELECT count(*) FROM lexicon.personal_lexical_relations "
                "WHERE profile_id=:profile)"
            ),
            {"profile": uid(11)},
        )
    ).one()
    assert loaded == (100_000, 399_990)
    assert counts == loaded

    search_sql = text(
        "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT sense_id,label "
        "FROM lexicon.lexical_reference_entries WHERE reference_set_id=:reference "
        "AND label >= 'lemma-050000' ORDER BY label,sense_id LIMIT 100"
    )
    graph_sql = text(
        "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) WITH RECURSIVE walk(node,depth) AS ("
        "VALUES (CAST(:root AS uuid),0) UNION SELECT relation.target_sense_id,walk.depth+1 "
        "FROM walk JOIN lexicon.personal_lexical_relations relation "
        "ON relation.profile_id=:profile AND relation.source_sense_id=walk.node "
        "WHERE walk.depth<2) SELECT node,min(depth) FROM walk GROUP BY node "
        "ORDER BY min(depth),node LIMIT 500"
    )

    async def samples(statement, parameters) -> tuple[list[float], dict]:
        plans = []
        for _ in range(25):
            plan = await migration_session.scalar(statement, parameters)
            plans.append(plan[0])
        return [float(plan["Execution Time"]) for plan in plans], plans[-1]

    search_times, search_plan = await samples(search_sql, {"reference": uid(600_000)})
    graph_times, graph_plan = await samples(
        graph_sql,
        {"profile": uid(11), "root": uid(500_001)},
    )
    search_p95 = statistics.quantiles(search_times, n=20)[18]
    graph_p95 = statistics.quantiles(graph_times, n=20)[18]

    factory = async_sessionmaker(migration_session.bind, expire_on_commit=False)
    service = SqlWordBankService(factory)
    service_times = []
    for _ in range(25):
        started = time.perf_counter()
        result = await service.get_sense(
            account_id=uid(1),
            profile_id=uid(11),
            sense_id=uid(500_001),
            depth=2,
            edge_types=("association",),
            max_nodes=500,
        )
        service_times.append((time.perf_counter() - started) * 1000)
        assert len(result.nodes) <= 500
    service_p95 = statistics.quantiles(service_times, n=20)[18]

    assert search_p95 < 100, search_plan
    assert graph_p95 < 200, graph_plan
    assert service_p95 < 200, service_times
