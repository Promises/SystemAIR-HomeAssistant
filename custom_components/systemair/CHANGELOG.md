# Changelog

## 0.2.3

### Added
- Added Select entity for easy operation mode control
- Enhanced Fan entity to support all operation modes (auto, manual, crowded, refresh, fireplace, away, holiday)
- Implemented fan speed control using manual airflow registers
- Added support for controlling ventilation modes from both fan and select entities

## 0.2.2

### Added
- Added real-time entity updates from WebSocket messages
- Enhanced WebSocket handling to immediately refresh entities when receiving device updates

## 0.2.1

### Fixed
- Fixed thread safety issues with WebSocket message handling
- Improved WebSocket message format detection to work with DEVICE_STATUS_UPDATE events
- Enhanced error handling in WebSocket callbacks

## 0.2.0

### Fixed
- Fixed GraphQL query structure for the get_account_devices method
- Updated coordinator to handle multiple potential response structures
- Fixed property access patterns to match the actual SystemAIR-API model
- Implemented proper WebSocket connection handling
- Added explicit WebSocket disconnection on integration unload
- Fixed device information usage (identifier, model, version)
- Corrected temperature and user mode property access
- Added better error logging for API responses
- Fixed mapping of user modes to match the API constants

### Added
- Added air quality sensor
- Added ECO mode and free cooling binary sensors
- Added detailed README with installation and usage instructions
- Added more detailed debug logging
- Implemented WebSocket reconnection when refreshing tokens

### Changed
- Updated entity naming to match actual model properties
- Improved fan control logic to use actual airflow values
- Improved error handling for API communication
- Updated climate entity to use the actual temperature properties