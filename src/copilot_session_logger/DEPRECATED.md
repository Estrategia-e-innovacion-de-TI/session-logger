# Deprecated Python Logger

The Python implementation under `src/copilot_session_logger` is retained only for backward compatibility with existing local installs and tests.

The active GitHub Copilot hook/session logger is the Bash implementation:

- `hooks/session-logger.sh`
- `lib/logger.sh`
- `lib/payload.sh`
- `lib/state.sh`
- `lib/transport.sh`

New hook configurations should call `bash ./hooks/session-logger.sh --event <hook-event>`.

