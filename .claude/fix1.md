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