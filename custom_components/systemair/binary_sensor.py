"""Binary sensor platform for SystemAIR integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from systemair_api.models.ventilation_unit import VentilationUnit

from .const import DOMAIN
from .coordinator import SystemairUpdateCoordinator


@dataclass
class SystemairBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Class describing SystemAIR binary sensor entities."""

    value_fn: Callable[[VentilationUnit], bool] = None


BINARY_SENSOR_TYPES = [
    # Active functions
    SystemairBinarySensorEntityDescription(
        key="active_heating",
        name="Heating active",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda unit: unit.active_functions.get('heating', False),
    ),
    SystemairBinarySensorEntityDescription(
        key="active_cooling",
        name="Cooling active",
        device_class=BinarySensorDeviceClass.COLD,
        value_fn=lambda unit: unit.active_functions.get('cooling', False),
    ),
    SystemairBinarySensorEntityDescription(
        key="active_defrosting",
        name="Defrosting active",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:snowflake-melt",
        value_fn=lambda unit: unit.active_functions.get('defrosting', False),
    ),
    
    # Alarm indicators
    SystemairBinarySensorEntityDescription(
        key="filter_alarm",
        name="Filter alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:air-filter",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda unit: unit.get_filter_alarm(),
    ),
    
    # Other active functions
    SystemairBinarySensorEntityDescription(
        key="eco_mode",
        name="ECO mode active",
        icon="mdi:leaf",
        value_fn=lambda unit: unit.active_functions.get('eco_mode', False),
    ),
    SystemairBinarySensorEntityDescription(
        key="free_cooling",
        name="Free cooling active",
        icon="mdi:snowflake",
        value_fn=lambda unit: unit.active_functions.get('free_cooling', False),
    ),
    
    # Connection status - using available property from coordinator
    SystemairBinarySensorEntityDescription(
        key="connected",
        name="Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda unit: True,  # If we can get data, it's connected
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SystemAIR binary sensor platform."""
    coordinator: SystemairUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for unit_id, unit in coordinator.units.items():
        entities.extend(
            [
                SystemairBinarySensor(coordinator, unit_id, description)
                for description in BINARY_SENSOR_TYPES
            ]
        )

    async_add_entities(entities)


class SystemairBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a SystemAIR binary sensor."""

    entity_description: SystemairBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: SystemairUpdateCoordinator,
        unit_id: str,
        description: SystemairBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
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
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        if self.coordinator.data and self._unit_id in self.coordinator.data:
            unit = self.coordinator.data[self._unit_id]
            return self.entity_description.value_fn(unit)
        return None