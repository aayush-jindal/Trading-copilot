Open app/routers/strategies.py. Find where StrategyResult objects are converted to dicts for the JSON response. The Condition.passed field contains numpy.bool_ values from ta_engine.py which FastAPI cannot serialise, causing a 500 error.
Fix the serialisation so all values are cast to native Python types before returning. Specifically:

condition.passed must be bool(condition.passed)
Any other numpy types (numpy.float64, numpy.int64) in RiskLevels fields must be cast to float() or int() respectively

The right place to fix this is in the dict conversion helper in strategies.py — not in ta_engine.py or base.py. Read the file first to find the exact conversion point, then add the casts there.

Read BookStrategiesPanel.tsx and tools/knowledge_base/strategy_gen.py.
The strategies prop is currently typed as string | null but strategy_gen.py now returns a dict with keys strategies, best_opportunity, and signals_to_watch. Update this component to handle the new shape.
Two changes needed:

Update the prop type — strategies is now the parsed dict or null, not a string. Define the shape from the actual keys returned by strategy_gen.py.
Update the render — replace the single whitespace-pre-wrap font-mono div with structured rendering:

Map over strategies.strategies array — each item has name, conditions_status, conditions_detail, conviction, sources, confirmation_signals, invalidation_signals
Show best_opportunity section if not null — has strategy_name, rationale, conviction
List signals_to_watch if the array is non-empty



Keep the existing header, loading state, and error state unchanged. Only change the prop type and the content render block. Match the existing amber colour scheme and glass style throughout.
Also find where BookStrategiesPanel is used in AnalysisPage.tsx and update the prop being passed to match the new type — it is currently passing a string where it should pass the parsed dict.

# # 1.2 ADD TO CACHE claude output

Read tools/knowledge_base/strategy_gen.py, app/routers/analysis.py (find where /analyze/{ticker}/knowledge-strategies is handled), and app/database.py (understand the schema init pattern).
Add a DB cache for book strategy results with these two changes:
1. Add knowledge_strategy_cache table to app/database.py:

ticker TEXT
cache_date DATE
result JSONB
created_at TIMESTAMP DEFAULT NOW()
Primary key on (ticker, cache_date)

2. Add cache read/write in the knowledge-strategies route:

Before calling generate_strategies(ticker): query cache for (ticker, today)
If found: return cached result immediately, no Claude call
If not found: call generate_strategies(ticker), store result in cache, return it

The cache never invalidates within a trading day. Old entries can stay indefinitely — they are historical record. Do not add any expiry logic.
Also change the frontend so BookStrategiesPanel is not fetched automatically on page load. Instead show a "Generate book analysis" button. When clicked, fetch and display. If a cached result exists for today it returns instantly. If not, it calls Claude and the user waits the few seconds.
Do not change strategy_gen.py itself. The caching layer sits in the router.