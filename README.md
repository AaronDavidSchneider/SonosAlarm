![Logo](https://raw.githubusercontent.com/AaronDavidSchneider/SonosAlarm/master/logo%402x.png)

# OUTDATED: Merged into [Homeassistant](https://www.home-assistant.io/integrations/sonos/#alarm-support)

# Sonos Alarm

Custom component for Home Assistant to control your SONOS Alarm

![Example](https://raw.githubusercontent.com/AaronDavidSchneider/SonosAlarm/master/example.png)

**Features:**

- Switch your alarms on/off
- no configuration needed
- information about you alarms, like time, volume, etc in attributes

## Installation

**Install via HACS**

The custom component will soon be available via

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

**Manual Install**

If you want to install the custom commponent manually, add the folder `sonos_alarm/` to `YOUR_CONFIG_DIR/custom_components/`.

## Configuration
**As Integration:**

Go to the `Integrations pane` on your Home Assistant instance and search for `Sonos Alarm`.

**Advanced Use:**

You can also use configuration.yaml configurations to specify your specific network requirements.

Here is an example configuration:

```yaml
sonos_alarm:
   switch:
      hosts:
        - 192.168.178.22
        - 192.168.178.29
        - 192.168.178.24
```

For more information see: https://www.home-assistant.io/integrations/sonos/#advanced-use
(same idea, just use `sonos_alarm` and `switch` instead of `sonos` and `media_player`)

Many thanks for bringing this up [@Schmandre](https://github.com/Schmandre)!!!

## Exposed entities

- `switch.sonos_alarm_[id of your alarm]` for each of your SONOS Alarms

## Example Usage
Have a look at https://github.com/AaronDavidSchneider/SonosAlarmAutomation for automations using `sonos_alarm`
