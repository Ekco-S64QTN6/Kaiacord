from utils.infrastructure.logging.kaia_logger import log_warning, log_error

class SelfHealingSystem:
    """Execute functions with fallback strategies."""
    @staticmethod
    async def call_with_fallback(func, *args, **kwargs):
        from utils.infrastructure.system.yaml_config import config
        original_options = kwargs.get('options', {}).copy()  # Save GPU options
        
        try:
            return await func(*args, **kwargs)
        except Exception as e:
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

