# Transcription options for RoboListener

Research date: October 27, 2026. These are engineering recommendations, not a benchmark of this app on radio broadcasts.

## Recommendation

Keep the current local Faster Whisper engine for now. For a slower computer, start with **small, CPU, int8**, and one station; try tiny if the transcript falls further behind the live audio. Small models can miss words and names, so compare the transcript and alerts against the recording. Turbo or large-v3 may be worth trying on a more capable computer. The first use of each model downloads its weights.

Faster Whisper uses CTranslate2 and supports CPU quantization. Its published benchmarks are useful evidence, but they do not establish speed or accuracy for a particular computer, language, or radio stream. The current app explicitly maps automatic device selection to CPU. Its CTranslate2 backend does not use Apple's GPU; NVIDIA CUDA is a separate, manually selected option and requires compatible hardware and libraries. [Faster Whisper](https://github.com/SYSTRAN/faster-whisper), [CTranslate2 hardware support](https://github.com/OpenNMT/CTranslate2/blob/master/docs/hardware_support.md), [Whisper models and language performance](https://github.com/openai/whisper/blob/main/README.md).

## Candidates for the next evaluation

- **whisper.cpp:** supports quantization and Apple Silicon acceleration via Metal and Core ML. This is a strong candidate to test on Macs, but needs a separate integration and model files. [whisper.cpp](https://github.com/ggml-org/whisper.cpp)
- **Qwen3-ASR 0.6B:** covers 30 languages and Chinese dialects, including Spanish, Arabic and Persian. It requires a different runtime; its performance on low-powered computers and radio audio needs measurement. [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)
- **Moonshine:** smaller language-specific streaming models may suit a narrow set of languages on modest hardware, but would need a separate integration and language-specific evaluation. [Available models](https://github.com/moonshine-ai/moonshine/blob/main/docs/models/available-models.md)
- **Parakeet TDT v3:** a multilingual model covering 25 European languages; its language coverage excludes Arabic and Persian. Its different runtime and hardware requirements also need evaluation. [Model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)

## What to measure before changing engines

Use the same consented or otherwise appropriate representative radio recordings across engines: speech with music, accents, noisy connections, multiple speakers, and the languages users actually monitor. Compare transcript accuracy and keyword recall, false alerts, processing time relative to audio duration, peak memory, and how far monitoring falls behind with one and several stations. Keep the recordings and transcripts available for human verification: speech recognition can omit or invent words, especially on difficult audio. A model's published score is not proof of suitability for this task.
