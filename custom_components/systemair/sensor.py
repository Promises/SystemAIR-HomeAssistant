"""Sensor platform for SystemAIR integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from systemair_api.models.ventilation_unit import VentilationUnit

from .const import DOMAIN
from .coordinator import SystemairUpdateCoordinator


@dataclass
class SystemairSensorEntityDescription(SensorEntityDescription):
    """Class describing SystemAIR sensor entities."""

    value_fn: Callable[[VentilationUnit], Any] = None


SENSOR_TYPES = [
    # Temperature sensors
    SystemairSensorEntityDescription(
        key="room_temp",
        name="Room temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda unit: unit.temperature,
    ),
    SystemairSensorEntityDescription(
        key="outdoor_temp",
        name="Outdoor temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda unit: unit.temperatures.get('oat'),
    ),
    SystemairSensorEntityDescription(
        key="supply_temp",
        name="Supply temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda unit: unit.temperatures.get('sat'),
    ),
    
    # Humidity sensors
    SystemairSensorEntityDescription(
        key="humidity",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda unit: unit.humidity,
    ),
    
    # Air quality sensor
    SystemairSensorEntityDescription(
        key="air_quality",
        name="Air Quality",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda unit: unit.air_quality,
    ),
    
    # Operation mode
    SystemairSensorEntityDescription(
        key="user_mode",
        name="Operation mode",
        icon="mdi:fan",
        value_fn=lambda unit: unit.user_mode_name,
    ),
    
    # User mode remaining time
    SystemairSensorEntityDescription(
        key="user_mode_remaining_time",
        name="Mode remaining time",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda unit: round(getattr(unit, 'user_mode_remaining_time', 0) / 60, 1) if getattr(unit, 'user_mode_remaining_time', None) is not None else None,
    ),
    
    # Removed airflow percentage sensor as it doesn't exist
    
    # Filter status - using active_alarms as a proxy for filter status
    SystemairSensorEntityDescription(
        key="filter_status",
        name="Filter status",
        icon="mdi:air-filter",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda unit: "Replace" if unit.get_filter_alarm() else "OK",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SystemAIR sensor platform."""
    coordinator: SystemairUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for unit_id, unit in coordinator.units.items():
        entities.extend(
            [
                SystemairSensor(coordinator, unit_id, description)
                for description in SENSOR_TYPES
            ]
        )

    async_add_entities(entities)


class SystemairSensor(CoordinatorEntity, SensorEntity):
    """Representation of a SystemAIR sensor."""

    entity_description: SystemairSensorEntityDescription

    def __init__(
        self,
        coordinator: SystemairUpdateCoordinator,
        unit_id: str,
        description: SystemairSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._unit_id = unit_id
        self._unit = coordinator.units[unit_id]
        self._attr_unique_id = f"{unit_id}_{description.key}"
        self._attr_name = f"{self._unit.name} {description.name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, unit_id)},
            "name": self._unit.name,
            "manufacturer": "Systemair",
            "model": self._unit.model or "Systemair Ventilation Unit",
            "sw_version": next((v.get("version") for v in self._unit.versions if v.get("type") == "SW"), None),
        }

    @property
    def native_value(self) -> Any:
        """Return the value of the sensor."""
        if self.coordinator.data and self._unit_id in self.coordinator.data:
            unit = self.coordinator.data[self._unit_id]
            return self.entity_description.value_fn(unit)
        return None