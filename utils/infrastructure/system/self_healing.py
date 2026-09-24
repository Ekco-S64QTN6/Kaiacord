from utils.infrastructure.logging.kaia_logger import log_warning, log_error

# Ollama aborts a generation that emits the same token too many times in a
# row and answers 500 "prediction aborted, token repeat limit reached". It is
# what happens when someone asks for a row of dots, a drawn line or a
# repeated word: the conversation is fine and the sampling is not.
REPEAT_LIMIT = "token repeat limit"
REPEAT_PENALTY = 1.3


def _is_repeat_abort(exc: Exception) -> bool:
    return REPEAT_LIMIT in str(exc)


class SelfHealingSystem:
    """Execute functions with fallback strategies."""
    @staticmethod
    async def call_with_fallback(func, *args, **kwargs):
        from utils.infrastructure.system.yaml_config import config
        original_options = kwargs.get('options', {}).copy()  # Save GPU options

        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if _is_repeat_abort(e):
                # Keep every message: cutting the history here is what made
                # her answer "commence." to a request she had just agreed to.
                # A repeat penalty is a sampling option, so it does not
                # reload the runner.
                log_warning("Generation looped on one token (Ollama's repeat limit); "
                            f"retrying with repeat_penalty {REPEAT_PENALTY}, full context kept.")
                if 'options' in kwargs:
                    kwargs['options'] = {
                        **original_options,
                        'repeat_penalty': max(REPEAT_PENALTY, original_options.get('repeat_penalty', 1.0)),
                        'repeat_last_n': 64,
                    }
            else:
                log_warning(f"Primary strategy failed: {e}. Trying simplified fallback...")

                # Fallback: Reduce context but PRESERVE GPU SETTINGS
                if 'messages' in kwargs:
                    # Keep only system and last few messages
                    kwargs['messages'] = [kwargs['messages'][0]] + kwargs['messages'][-2:]

                if 'options' in kwargs:
                    # Merge: Keep original GPU options, only adjust response length
                    fallback_predict = config.generation_fallback_num_predict
                    kwargs['options'] = {**original_options, 'num_predict': fallback_predict}

            try:
                return await func(*args, **kwargs)
            except Exception as e2:
                log_error(f"Fallback failed: {e2}")
                raise e2
