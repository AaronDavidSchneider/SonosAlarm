"""Switch for Sonos alarms."""
import asyncio

from datetime import timedelta
from datetime import datetime
import logging
from typing import Callable

import socket
import pysonos
from pysonos import alarms
from pysonos.exceptions import SoCoUPnPException, SoCoException
from pysonos.events_base import SubscriptionBase
from pysonos.core import SoCo

from homeassistant.components.switch import ENTITY_ID_FORMAT, SwitchEntity
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify

from . import (
    ATTR_INCLUDE_LINKED_ZONES,
    ATTR_TIME,
    ATTR_VOLUME,
    CONF_ADVERTISE_ADDR,
    CONF_INTERFACE_ADDR,
    CONF_HOSTS,
    DOMAIN as SONOS_DOMAIN,
    DATA_SONOS
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = 10
DISCOVERY_INTERVAL = 60
SEEN_EXPIRE_TIME = 3.5 * DISCOVERY_INTERVAL

ATTR_DURATION = "duration"
ATTR_ID = "alarm_id"
ATTR_PLAY_MODE = "play_mode"
ATTR_RECURRENCE = "recurrence"
ATTR_SCHEDULED_TODAY = "scheduled_today"

class SonosData:
    """Storage class for platform global data."""

    def __init__(self) -> None:
        """Initialize the data."""
        self.entities = []
        self.discovered = []
        self.topology_condition = asyncio.Condition()
        self.discovery_thread = None
        self.hosts_heartbeat = None

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Sonos platform. Obsolete."""
    _LOGGER.error(
        "Loading Sonos alarms by switch platform config is no longer supported"
    )

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up Sonos from a config entry."""
    if DATA_SONOS not in hass.data:
        hass.data[DATA_SONOS] = SonosData()

    config = hass.data[SONOS_DOMAIN].get("switch", {})
    _LOGGER.debug("Reached async_setup_entry of alarm, config=%s", config)

    advertise_addr = config.get(CONF_ADVERTISE_ADDR)
    if advertise_addr:
        pysonos.config.EVENT_ADVERTISE_IP = advertise_addr

    def _stop_discovery(event) -> None:
        data = hass.data[DATA_SONOS]
        if data.discovery_thread:
            data.discovery_thread.stop()
            data.discovery_thread = None
        if data.hosts_heartbeat:
            data.hosts_heartbeat()
            data.hosts_heartbeat = None

    def _discovery(now=None):
        """Discover players from network or configuration."""
        hosts = config.get(CONF_HOSTS)
        _LOGGER.debug(hosts)

        def _discovered_alarm(soco):
            """Handle a (re)discovered player."""
            try:
                _LOGGER.debug("Reached _discovered_player, soco=%s", soco)
                for one_alarm in alarms.get_alarms(soco):
                    if one_alarm.zone == soco and one_alarm._alarm_id not in hass.data[DATA_SONOS].discovered:
                        _LOGGER.debug("Adding new alarm")
                        hass.data[DATA_SONOS].discovered.append(one_alarm._alarm_id)
                        hass.add_job(
                            async_add_entities, [SonosAlarmSwitch(one_alarm)],
                        )
                    else:
                        entity = _get_entity_from_alarm_id(hass, one_alarm._alarm_id)
                        if entity and (entity.soco == soco or not entity.available):
                            _LOGGER.debug("Seen %s", entity)
                            hass.add_job(entity.async_seen(soco))  # type: ignore
            except SoCoUPnPException as ex:
                _LOGGER.debug("SoCoException, ex=%s", ex)

        if hosts:
            for host in hosts:
                try:
                    _LOGGER.debug("Testing %s", host)
                    player = pysonos.SoCo(socket.gethostbyname(host))
                    if player.is_visible:
                        # Make sure that the player is available
                        _ = player.volume

                        _discovered_alarm(player)
                except (OSError, SoCoUPnPException) as ex:
                    _LOGGER.debug("Exception %s", ex)
                    if now is None:
                        _LOGGER.warning("Failed to initialize '%s'", host)

            _LOGGER.debug("Tested all hosts")
            hass.data[DATA_SONOS].hosts_heartbeat = hass.helpers.event.call_later(
                DISCOVERY_INTERVAL, _discovery)
        else:
            _LOGGER.debug("Starting discovery thread")
            hass.data[DATA_SONOS].discovery_thread = pysonos.discover_thread(
                _discovered_alarm,
                interval=DISCOVERY_INTERVAL,
                interface_addr=config.get(CONF_INTERFACE_ADDR),
            )
            hass.data[DATA_SONOS].discovery_thread.name = "Sonos-Discovery"

    _LOGGER.debug("Adding discovery job")
    hass.async_add_executor_job(_discovery)
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop_discovery)

def _get_entity_from_alarm_id(hass, id):
    """Return SonosEntity from alarm id."""
    entities = hass.data[DATA_SONOS].entities
    for entity in entities:
        if id == entity.alarm_id:
            return entity
    return None


class SonosAlarmSwitch(SwitchEntity):
    """Switch class for Sonos alarms."""

    def __init__(self, alarm):
        _LOGGER.debug("Init Sonos alarms switch.")
        """Init Sonos alarms switch."""

        self._subscriptions: list[SubscriptionBase] = []
        self._poll_timer = None
        self._seen_timer = None

        self._icon = "mdi:alarm"
        self.alarm = alarm
        self.alarm_id = self.alarm._alarm_id
        self._unique_id = "{}-{}".format(SONOS_DOMAIN,self.alarm_id)
        _entity_id = slugify("sonos_alarm_{}".format(self.alarm_id))
        self.entity_id = ENTITY_ID_FORMAT.format(_entity_id)

        speaker_info = self.alarm.zone.get_speaker_info(True)
        self._speaker_name: str = speaker_info["zone_name"]
        self._model: str = speaker_info["model_name"]
        self._sw_version: str = speaker_info["software_version"]
        self._mac_address: str = speaker_info["mac_address"]
        self._unique_player_id: str = self.alarm.zone.uid

        self._get_current_alarm_instance()

        self._is_on = self.alarm.enabled
        self._attributes = {
            ATTR_ID: str(self.alarm_id),
            ATTR_TIME: str(self.alarm.start_time),
            ATTR_VOLUME: self.alarm.volume / 100,
            ATTR_DURATION: str(self.alarm.duration),
            ATTR_INCLUDE_LINKED_ZONES: self.alarm.include_linked_zones,
            ATTR_RECURRENCE: str(self.alarm.recurrence),
            ATTR_PLAY_MODE: str(self.alarm.play_mode),
            ATTR_SCHEDULED_TODAY: self._is_today
        }

        self._name = "Sonos Alarm {} {} {}".format(
            self._speaker_name,
            self.alarm.recurrence.title(),
            str(self.alarm.start_time)[0:5]
        )

        super().__init__()
        _LOGGER.debug("reached end of init")

    def _get_current_alarm_instance(self):
        """Function that retrieves the current alarms and returns if the alarm is available or not."""
        current_alarms = alarms.get_alarms(self.alarm.zone)

        if self.alarm in current_alarms:
            return True
        else:
            return False

    async def async_added_to_hass(self) -> None:
        """Subscribe sonos events."""
        await self.async_seen(self.soco)

        self.hass.data[DATA_SONOS].entities.append(self)

    async def async_seen(self, player: SoCo) -> None:
        """Record that this player was seen right now."""
        was_available = self.available
        _LOGGER.debug("Async seen: %s, was_available: %s", player, was_available)

        if self._seen_timer:
            self._seen_timer()

        self._seen_timer = self.hass.helpers.event.async_call_later(
            SEEN_EXPIRE_TIME, self.async_unseen
        )

        if was_available:
            return

        self._poll_timer = self.hass.helpers.event.async_track_time_interval(
            self.update, timedelta(seconds=SCAN_INTERVAL)
        )

        done = await self._async_attach_player()
        if not done:
            assert self._seen_timer is not None
            self._seen_timer()
            await self.async_unseen()

        self.async_write_ha_state()

    async def async_unseen(self, now = None) -> None:
        """Make this player unavailable when it was not seen recently."""
        self._seen_timer = None

        if self._poll_timer:
            self._poll_timer()
            self._poll_timer = None

        for subscription in self._subscriptions:
            await subscription.unsubscribe()

        self._subscriptions = []

        self.async_write_ha_state()

    @property
    def soco(self) -> SoCo:
        """Return soco object."""
        return self.alarm.zone

    async def _async_attach_player(self) -> bool:
        """Get basic information and add event subscriptions."""
        try:
            player = self.soco

            if self._subscriptions:
                raise RuntimeError(
                    f"Attempted to attach subscriptions to player: {player} "
                    f"when existing subscriptions exist: {self._subscriptions}"
                )

            await self._subscribe(player.alarmClock, self.async_update_alarm)
            return True
        except SoCoException as ex:
            _LOGGER.warning("Could not connect %s: %s", self.entity_id, ex)
            return False

    def update(self, now = None) -> None:
        """Retrieve latest state."""
        try:
            self.update_alarm()
        except SoCoUPnPException as exc:
            _LOGGER.warning(
                "Home Assistant couldn't update the state of the alarm %s",
                exc,
                exc_info=True,
            )

    async def async_remove_if_not_available(self, event = None):
        is_available = await self.hass.async_add_executor_job(self._get_current_alarm_instance)

        if is_available:
            return

        await self.async_unseen()

        self.hass.data[DATA_SONOS].entities.remove(self)
        self.hass.data[DATA_SONOS].discovered.remove(self.alarm_id)

        entity_registry = er.async_get(self.hass)
        entity_registry.async_remove(self.entity_id)


    @callback
    def async_update_alarm(self, event = None):
        """Update information about alarm """
        self.hass.async_add_job(self.async_remove_if_not_available, event)
        self.hass.async_add_executor_job(self.update_alarm, event)


    def update_alarm(self, event = None):
        """Retrieve latest state."""
        _LOGGER.debug("updating alarms")

        def _update_device():
            """update the device, since this alarm moved to a different player"""
            device_registry = dr.async_get(self.hass)
            entity_registry = er.async_get(self.hass)
            entry_id = entity_registry.async_get(self.entity_id).config_entry_id

            new_device = device_registry.async_get_or_create(config_entry_id=entry_id,
                                                             identifiers={(SONOS_DOMAIN, self._unique_player_id)},
                                                             connections={
                                                                 (dr.CONNECTION_NETWORK_MAC, self._mac_address)})
            if not entity_registry.async_get(self.entity_id).device_id == new_device.id:
                entity_registry._async_update_entity(self.entity_id, device_id=new_device.id)

        self._is_on = self.alarm.enabled

        if self._unique_player_id != self.alarm.zone.uid:
            speaker_info = self.alarm.zone.get_speaker_info(True)
            self._speaker_name: str = speaker_info["zone_name"]
            self._model: str = speaker_info["model_name"]
            self._sw_version: str = speaker_info["software_version"]
            self._mac_address: str = speaker_info["mac_address"]
            self._unique_player_id: str = self.alarm.zone.uid
            _update_device()


        self._name = "Sonos Alarm {} {} {}".format(
            self._speaker_name,
            self.alarm.recurrence.title(),
            str(self.alarm.start_time)[0:5]
        )

        self._attributes[ATTR_ID] = str(self.alarm_id)
        self._attributes[ATTR_TIME] = str(self.alarm.start_time)
        self._attributes[ATTR_DURATION] = str(self.alarm.duration)
        self._attributes[ATTR_RECURRENCE] = str(self.alarm.recurrence)
        self._attributes[ATTR_VOLUME] = self.alarm.volume / 100
        self._attributes[ATTR_PLAY_MODE] = str(self.alarm.play_mode)
        self._attributes[ATTR_SCHEDULED_TODAY] = self._is_today
        self._attributes[
            ATTR_INCLUDE_LINKED_ZONES
        ] = self.alarm.include_linked_zones

        self.schedule_update_ha_state()

        _LOGGER.debug("successfully updated alarms")

    async def _subscribe(
        self, target: SubscriptionBase, sub_callback: Callable
    ) -> None:
        """Create a sonos subscription."""
        subscription = await target.subscribe(auto_renew=True)
        subscription.callback = sub_callback
        self._subscriptions.append(subscription)

    @property
    def _is_today(self):
        recurrance = self.alarm.recurrence
        timestr = int(datetime.today().strftime('%w'))
        if recurrance[:2] == "ON":
            if str(timestr) in recurrance:
                return True
            else:
                return False
        else:
            if recurrance == "DAILY":
                return True
            elif recurrance == "ONCE":
                return True
            elif recurrance == "WEEKDAYS" and int(timestr) not in [0, 7]:
                return True
            elif recurrance == "WEEKENDS" and int(timestr) not in range(1, 7):
                return True
            else:
                return False

    @property
    def should_poll(self) -> bool:
        """Return that we should not be polled (we handle that internally)."""
        return False

    @property
    def name(self):
        """Return name of Sonos alarm switch."""
        return self._name

    @property
    def icon(self):
        """Return icon of Sonos alarm switch."""
        return self._icon

    @property
    def device_state_attributes(self):
        """Return attributes of Sonos alarm switch."""
        return self._attributes

    @property
    def is_on(self):
        """Return state of Sonos alarm switch."""
        return self._is_on

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def device_info(self) -> dict:
        """Return information about the device."""
        return {
            "identifiers": {(SONOS_DOMAIN, self._unique_player_id)},
            "name": self._speaker_name,
            "model": self._model.replace("Sonos ", ""),
            "sw_version": self._sw_version,
            "connections": {(dr.CONNECTION_NETWORK_MAC, self._mac_address)},
            "manufacturer": "Sonos",
            "suggested_area": self._speaker_name,
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._seen_timer is not None

    async def async_turn_on(self, **kwargs) -> None:
        """Turn alarm switch on."""
        sucess = await self.async_handle_switch_on_off(turn_on=True)
        if sucess:
            self._is_on = True

    async def async_turn_off(self, **kwargs) -> None:
        """Turn alarm switch off."""
        sucess = await self.async_handle_switch_on_off(turn_on=False)
        if sucess:
            self._is_on = False

    async def async_handle_switch_on_off(self, turn_on: bool) -> bool:
        """Handle turn on/off of alarm switch."""
        # pylint: disable=import-error
        try:
            self.alarm.enabled = turn_on
            await self.hass.async_add_executor_job(self.alarm.save)
            return True
        except SoCoUPnPException as exc:
            _LOGGER.warning(
                "Home Assistant couldnt switch the alarm %s", exc, exc_info=True
            )
            return False
