# Core Assistant Engine Scaffold

This scaffold lives in `friday/assistant_engine` and provides a modular runtime for:

- offline wake-word detection (`KeywordWakeWordDetector`)
- running STT stream updates (`RunningTextSTT`)
- intent classification (`RuleBasedIntentClassifier`)
- local + cloud LLM bridges (`LocalLLMBridge`, `CloudLLMBridge`, `HybridLLMBridge`)
- TTS output adapter (`FileTTSAdapter`)
- automation execution (`InProcessAutomationExecutor`)
- async processing loops + event queue (`AssistantEngine`)

## Run

```powershell
friday-engine
```

Type commands in the interactive prompt:

- `hey friday open notepad`
- `hey friday write a python function to parse json`

## Environment

- `FRIDAY_ENGINE_WAKE_WORDS`
- `FRIDAY_ENGINE_REQUIRE_WAKE_WORD`
- `FRIDAY_ENGINE_CLOUD_LLM_ENABLED`
- `FRIDAY_ENGINE_CLOUD_LLM_BASE_URL`
- `FRIDAY_ENGINE_CLOUD_LLM_MODEL`
- `FRIDAY_ENGINE_CLOUD_LLM_API_KEY`
- `FRIDAY_ENGINE_TTS_OUTPUT_DIR`

## Notes

- The default STT and TTS adapters are local scaffolds for a reliable development loop.
- Replace adapters by implementing interfaces in `friday/assistant_engine/interfaces.py`.
