import QtQuick
import QtQuick.Controls
import QtQuick.Shapes
import Quickshell.Io
import ".."
import "../services"

Item {
  id: settingsPanel

  property var colors
  property bool settingsOpen: false
  property string activeTab: "selector"
  property bool openDownward: false

  property var _ollamaModels: []
  property bool _ollamaModelsFetching: false
  property string _ollamaFetchStdout: ""
  property string _lastConvertResult: ""
  property string _lastOptimizeResult: ""

  property var _ollamaFetchProc: Process {
    onExited: function(code) {
      settingsPanel._ollamaModelsFetching = false
      if (code === 0) {
        try {
          var resp = JSON.parse(settingsPanel._ollamaFetchStdout.trim())
          var names = (resp.models || []).map(function(m) { return m.name })
          names.sort()
          settingsPanel._ollamaModels = names
        } catch(e) { settingsPanel._ollamaModels = [] }
      } else { settingsPanel._ollamaModels = [] }
    }
    stdout: SplitParser {
      onRead: function(data) { settingsPanel._ollamaFetchStdout += data }
    }
  }

  function _fetchOllamaModels() {
    var url = Config.ollamaUrl || "http://localhost:11434"
    _ollamaModelsFetching = true
    _ollamaFetchStdout = ""
    _ollamaFetchProc.command = ["sh", "-c", "curl -s --max-time 5 '" + url + "/api/tags'"]
    _ollamaFetchProc.running = true
  }

  Connections {
    target: Config
    function onOllamaEnabledChanged() {
      if (!Config.ollamaEnabled && settingsPanel.activeTab === "ollama")
        settingsPanel.activeTab = "features"
    }
  }

  Connections {
    target: ImageOptimizeService
    function onFinished(optimized, skippedCount, failed) {
      var parts = []
      if (optimized > 0) parts.push(optimized + " optimized")
      if (skippedCount > 0) parts.push(skippedCount + " skipped")
      if (failed > 0) parts.push(failed + " failed")
      settingsPanel._lastOptimizeResult = parts.join(" · ") || "Nothing to optimize"
    }
  }

  z: 102
  width: 580
  height: tabRow.height + contentLoader.height + 36

  visible: settingsOpen
  opacity: settingsOpen ? 1 : 0
  scale: settingsOpen ? 1 : 0.9
  transformOrigin: openDownward ? Item.Top : Item.Bottom
  Behavior on opacity { NumberAnimation { duration: Style.animFast; easing.type: Easing.OutCubic } }
  Behavior on scale { NumberAnimation { duration: Style.animFast; easing.type: Easing.OutCubic } }

  signal closeRequested()

  Keys.onEscapePressed: closeRequested()
  focus: settingsOpen

  MouseArea {
    anchors.fill: parent
    acceptedButtons: Qt.LeftButton | Qt.RightButton
    onClicked: function(mouse) {
      if (mouse.button === Qt.RightButton) settingsPanel.closeRequested()
    }
  }

  FileView {
    id: _selectorConfigFile
    path: Config.configDir + "/config.json"
    preload: true
  }

  function _readConfig() {
    _selectorConfigFile.reload()
    try { return JSON.parse(_selectorConfigFile.text()) } catch(e) { return {} }
  }

  function _saveField(key, value) {
    var data = _readConfig()
    if (!data.components) data.components = {}
    if (typeof data.components.wallpaperSelector !== "object" || data.components.wallpaperSelector === null)
      data.components.wallpaperSelector = { enabled: true }
    data.components.wallpaperSelector[key] = value
    _selectorConfigFile.setText(JSON.stringify(data, null, 2) + "\n")
  }

  function _saveSelectorFields(fields) {
    var data = _readConfig()
    if (!data.components) data.components = {}
    if (typeof data.components.wallpaperSelector !== "object" || data.components.wallpaperSelector === null)
      data.components.wallpaperSelector = { enabled: true }
    for (var key in fields)
      data.components.wallpaperSelector[key] = fields[key]
    _selectorConfigFile.setText(JSON.stringify(data, null, 2) + "\n")
  }

  function _saveConfigKey(path, value) {
    var data = _readConfig()
    var parts = path.split(".")
    var obj = data
    for (var i = 0; i < parts.length - 1; i++) {
      if (typeof obj[parts[i]] !== "object" || obj[parts[i]] === null)
        obj[parts[i]] = {}
      obj = obj[parts[i]]
    }
    obj[parts[parts.length - 1]] = value
    _selectorConfigFile.setText(JSON.stringify(data, null, 2) + "\n")
  }

  function _applyPreset(expanded, sliceH, sliceW, visible, gap, skew) {
    _saveSelectorFields({
      expandedWidth: expanded,
      sliceHeight: sliceH,
      sliceWidth: sliceW,
      visibleCount: visible,
      sliceSpacing: gap,
      skewOffset: skew
    })
  }

  function _builtInPresetModel() {
    if (Config.displayMode === "hex") {
      return [
        { label: "XS", hexRadius: 70,  hexRows: 1, hexCols: 5, hexScrollStep: 1, hexArcIntensity: 0.8 },
        { label: "S",  hexRadius: 90,  hexRows: 1, hexCols: 6, hexScrollStep: 1, hexArcIntensity: 1.0 },
        { label: "M",  hexRadius: 115, hexRows: 2, hexCols: 7, hexScrollStep: 1, hexArcIntensity: 1.2 },
        { label: "L",  hexRadius: 140, hexRows: 2, hexCols: 7, hexScrollStep: 1, hexArcIntensity: 1.2 },
        { label: "XL", hexRadius: 170, hexRows: 3, hexCols: 8, hexScrollStep: 1, hexArcIntensity: 1.3 }
      ]
    }
    if (Config.displayMode === "wall") {
      return [
        { label: "XS", gridColumns: 7, gridRows: 3, gridThumbWidth: 160, gridThumbHeight: 90 },
        { label: "S",  gridColumns: 6, gridRows: 3, gridThumbWidth: 220, gridThumbHeight: 124 },
        { label: "M",  gridColumns: 5, gridRows: 3, gridThumbWidth: 280, gridThumbHeight: 158 },
        { label: "L",  gridColumns: 4, gridRows: 3, gridThumbWidth: 340, gridThumbHeight: 191 },
        { label: "XL", gridColumns: 3, gridRows: 2, gridThumbWidth: 460, gridThumbHeight: 259 }
      ]
    }
    return [
      { label: "XS", expanded: 360,  sliceH: 200, sliceW: 52,  visibleCount: 20, gap: -30, skew: 16 },
      { label: "S",  expanded: 480,  sliceH: 270, sliceW: 68,  visibleCount: 18, gap: -30, skew: 20 },
      { label: "M",  expanded: 768,  sliceH: 432, sliceW: 108, visibleCount: 14, gap: -30, skew: 28 },
      { label: "L",  expanded: 924,  sliceH: 520, sliceW: 135, visibleCount: 12, gap: -30, skew: 35 },
      { label: "XL", expanded: 1280, sliceH: 720, sliceW: 180, visibleCount: 9,  gap: -30, skew: 45 }
    ]
  }

  function _applyBuiltInPreset(preset) {
    if (Config.displayMode === "hex") {
      _saveSelectorFields({
        hexRadius: preset.hexRadius,
        hexRows: preset.hexRows,
        hexCols: preset.hexCols,
        hexScrollStep: preset.hexScrollStep,
        hexArc: true,
        hexArcIntensity: preset.hexArcIntensity,
        activeCustomPreset: ""
      })
    } else if (Config.displayMode === "wall") {
      _saveSelectorFields({
        gridColumns: preset.gridColumns,
        gridRows: preset.gridRows,
        gridThumbWidth: preset.gridThumbWidth,
        gridThumbHeight: preset.gridThumbHeight,
        activeCustomPreset: ""
      })
    } else {
      _saveSelectorFields({
        expandedWidth: preset.expanded,
        sliceHeight: preset.sliceH,
        sliceWidth: preset.sliceW,
        visibleCount: preset.visibleCount,
        sliceSpacing: preset.gap,
        skewOffset: preset.skew,
        activeCustomPreset: ""
      })
    }
  }

  function _isBuiltInPresetActive(preset) {
    if (Config.displayMode === "hex") {
      return Config.hexRadius === preset.hexRadius
        && Config.hexRows === preset.hexRows
        && Config.hexCols === preset.hexCols
        && Math.round(Config.hexArcIntensity * 10) === Math.round(preset.hexArcIntensity * 10)
    }
    if (Config.displayMode === "wall") {
      return Config.gridColumns === preset.gridColumns
        && Config.gridRows === preset.gridRows
        && Config.gridThumbWidth === preset.gridThumbWidth
        && Config.gridThumbHeight === preset.gridThumbHeight
    }
    return Config.wallpaperExpandedWidth === preset.expanded
      && Config.wallpaperSliceHeight === preset.sliceH
      && Config.wallpaperSliceWidth === preset.sliceW
      && Config.wallpaperVisibleCount === preset.visibleCount
  }

  function _builtInPresetTooltip(preset) {
    if (Config.displayMode === "hex")
      return "r" + preset.hexRadius + " " + preset.hexRows + "×" + preset.hexCols
    if (Config.displayMode === "wall")
      return preset.gridColumns + "×" + preset.gridRows + " · " + preset.gridThumbWidth + "×" + preset.gridThumbHeight
    return preset.expanded + "×" + preset.sliceH + " (16:9)"
  }

  function _saveCustomPreset(slot) {
    var data = _readConfig()
    if (!data.components) data.components = {}
    if (typeof data.components.wallpaperSelector !== "object" || data.components.wallpaperSelector === null)
      data.components.wallpaperSelector = { enabled: true }
    if (!data.components.wallpaperSelector.customPresets)
      data.components.wallpaperSelector.customPresets = {}
    var key = slot + "_" + Config.displayMode
    var preset = {}
    if (Config.displayMode === "slices") {
      preset = {
        expandedWidth: Config.wallpaperExpandedWidth,
        sliceHeight: Config.wallpaperSliceHeight,
        sliceWidth: Config.wallpaperSliceWidth,
        visibleCount: Config.wallpaperVisibleCount,
        sliceSpacing: Config.wallpaperSliceSpacing,
        skewOffset: Config.wallpaperSkewOffset
      }
    } else if (Config.displayMode === "hex") {
      preset = {
        hexRadius: Config.hexRadius,
        hexRows: Config.hexRows,
        hexCols: Config.hexCols,
        hexScrollStep: Config.hexScrollStep,
        hexArc: Config.hexArc,
        hexArcIntensity: Config.hexArcIntensity
      }
    } else if (Config.displayMode === "wall") {
      preset = {
        gridColumns: Config.gridColumns,
        gridRows: Config.gridRows,
        gridThumbWidth: Config.gridThumbWidth,
        gridThumbHeight: Config.gridThumbHeight
      }
    }
    data.components.wallpaperSelector.customPresets[key] = preset
    _selectorConfigFile.setText(JSON.stringify(data, null, 2) + "\n")
  }

  function _loadCustomPreset(slot) {
    var key = slot + "_" + Config.displayMode
    var p = Config.wallpaperCustomPresets[key]
    if (!p) return
    if (Config.displayMode === "slices") {
      _applyPreset(p.expandedWidth, p.sliceHeight, p.sliceWidth, p.visibleCount, p.sliceSpacing, p.skewOffset)
    } else if (Config.displayMode === "hex") {
      var hexFields = {}
      if (p.hexRadius !== undefined) hexFields.hexRadius = p.hexRadius
      if (p.hexRows !== undefined) hexFields.hexRows = p.hexRows
      if (p.hexCols !== undefined) hexFields.hexCols = p.hexCols
      if (p.hexScrollStep !== undefined) hexFields.hexScrollStep = p.hexScrollStep
      if (p.hexArc !== undefined) hexFields.hexArc = p.hexArc
      if (p.hexArcIntensity !== undefined) hexFields.hexArcIntensity = p.hexArcIntensity
      settingsPanel._saveSelectorFields(hexFields)
    } else if (Config.displayMode === "wall") {
      var wallFields = {}
      if (p.gridColumns !== undefined) wallFields.gridColumns = p.gridColumns
      if (p.gridRows !== undefined) wallFields.gridRows = p.gridRows
      if (p.gridThumbWidth !== undefined) wallFields.gridThumbWidth = p.gridThumbWidth
      if (p.gridThumbHeight !== undefined) wallFields.gridThumbHeight = p.gridThumbHeight
      settingsPanel._saveSelectorFields(wallFields)
    }
  }

  property int _tabSkew: 14

  Row {
    id: tabRow
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.top: parent.top
    anchors.topMargin: 12
    spacing: -settingsPanel._tabSkew
    z: 11

    add: Transition {
      NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Style.animNormal; easing.type: Easing.OutCubic }
      NumberAnimation { property: "scale"; from: 0.8; to: 1; duration: Style.animNormal; easing.type: Easing.OutCubic }
    }
    move: Transition {
      NumberAnimation { properties: "x"; duration: Style.animNormal; easing.type: Easing.OutCubic }
    }

    Repeater {
      model: {
        var tabs = [
          { key: "selector",  label: "SELECTOR" },
          { key: "general",   label: "GENERAL" },
          { key: "paths",     label: "PATHS" },
          { key: "wallhaven", label: "WALLHAVEN" },
          { key: "features",  label: "FEATURES" },
          { key: "performance", label: "PERFORMANCE" },
          { key: "keybinds",  label: "KEYBINDS" }
        ]
        if (Config.ollamaEnabled) tabs.push({ key: "ollama", label: "OLLAMA" })
        return tabs
      }

      FilterButton {
        colors: settingsPanel.colors
        label: modelData.label
        skew: settingsPanel._tabSkew
        height: 28
        isActive: settingsPanel.activeTab === modelData.key
        onClicked: settingsPanel.activeTab = modelData.key
      }
    }
  }

  Item {
    id: contentLoader
    anchors.top: tabRow.bottom
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.margins: 12
    anchors.topMargin: 8
    height: {
      if (settingsPanel.activeTab === "selector") return selectorContent.implicitHeight
      if (settingsPanel.activeTab === "general") return generalContent.implicitHeight
      if (settingsPanel.activeTab === "ollama") return ollamaContent.implicitHeight
      if (settingsPanel.activeTab === "paths") return pathsContent.implicitHeight
      if (settingsPanel.activeTab === "wallhaven") return wallhavenContent.implicitHeight
      if (settingsPanel.activeTab === "features") return featuresContent.implicitHeight
      if (settingsPanel.activeTab === "performance") return performanceContent.implicitHeight
      if (settingsPanel.activeTab === "keybinds") return keybindsContent.implicitHeight
      return 0
    }
    Behavior on height { NumberAnimation { duration: Style.animFast; easing.type: Easing.OutCubic } }

    Row {
      id: selectorContent
      anchors.left: parent.left
      anchors.right: parent.right
      visible: settingsPanel.activeTab === "selector"
      spacing: 12

      Column {
        width: (parent.width - parent.spacing * 4 - 2) * 0.30
        spacing: 8

        Text {
          text: "LAYOUT"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        Row {
          width: parent.width; spacing: -4
          Repeater {
            model: [
              { key: "slices",  label: "Slices" },
              { key: "hex",     label: "Hex" },
              { key: "wall",    label: "Wall" }
            ]
            FilterButton {
              colors: settingsPanel.colors
              label: modelData.label
              skew: 8; height: 26
              isActive: Config.displayMode === modelData.key
              onClicked: settingsPanel._saveField("displayMode", modelData.key)
            }
          }
        }

        Item { width: 1; height: 2 }

        Text {
          text: "PRESETS"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        Row {
          width: parent.width; spacing: -4
          Repeater {
            model: settingsPanel._builtInPresetModel()
            FilterButton {
              colors: settingsPanel.colors
              label: modelData.label
              skew: 8; height: 26
              isActive: settingsPanel._isBuiltInPresetActive(modelData)
              onClicked: settingsPanel._applyBuiltInPreset(modelData)
              tooltip: settingsPanel._builtInPresetTooltip(modelData)
            }
          }
        }

        Row {
          width: parent.width; spacing: -4
          Repeater {
            model: ["C1", "C2", "C3", "C4"]
            FilterButton {
              property string presetKey: modelData + "_" + Config.displayMode
              property var presetData: Config.wallpaperCustomPresets[presetKey] || null
              property bool isEmpty: !presetData
              colors: settingsPanel.colors
              label: modelData
              skew: 8; height: 26
              isActive: !isEmpty && Config.wallpaperActiveCustomPreset === presetKey
              activeOpacity: isEmpty ? 0.35 : 1.0
              tooltip: {
                if (isEmpty) return "Click to save current"
                if (Config.displayMode === "slices") return presetData.expandedWidth + "×" + presetData.sliceHeight + " — Right-click overwrite · Click active to deactivate"
                if (Config.displayMode === "hex") return "r" + presetData.hexRadius + " " + presetData.hexRows + "×" + presetData.hexCols + " — Right-click overwrite · Click active to deactivate"
                if (Config.displayMode === "wall") return presetData.gridColumns + "×" + presetData.gridRows + " " + presetData.gridThumbWidth + "×" + presetData.gridThumbHeight + " — Right-click overwrite · Click active to deactivate"
                return ""
              }
              onClicked: {
                if (isEmpty) {
                  settingsPanel._saveCustomPreset(modelData)
                  settingsPanel._saveField("activeCustomPreset", presetKey)
                  return
                }
                if (isActive) {
                  settingsPanel._saveField("activeCustomPreset", "")
                  return
                }
                settingsPanel._loadCustomPreset(modelData)
                settingsPanel._saveField("activeCustomPreset", presetKey)
              }
              MouseArea {
                anchors.fill: parent; acceptedButtons: Qt.RightButton
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                  settingsPanel._saveCustomPreset(modelData)
                  settingsPanel._saveField("activeCustomPreset", presetKey)
                }
              }
            }
          }
        }

        Text {
          width: parent.width
          text: "C1-C4 son presets personalizados. Click guarda/carga, click en activo desactiva, click derecho sobrescribe."
          font.family: Style.fontFamily; font.pixelSize: 10; font.letterSpacing: 0.2
          color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.75) : Qt.rgba(1, 1, 1, 0.45)
          wrapMode: Text.WordWrap
          lineHeight: 1.25
        }
      }

      Rectangle {
        width: 1; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.primary.r, settingsPanel.colors.primary.g, settingsPanel.colors.primary.b, 0.1) : Qt.rgba(1, 1, 1, 0.08)
      }

      Column {
        width: (parent.width - parent.spacing * 4 - 2) * 0.35
        spacing: 6

        Text {
          text: Config.displayMode === "hex" ? "HEX GRID" : (Config.displayMode === "wall" ? "WALL" : "SIZE")
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsInput { visible: Config.displayMode === "slices"; colors: settingsPanel.colors; label: "Height"; value: Config.wallpaperSliceHeight; min: 200; max: 1200; onCommit: function(n) { settingsPanel._saveField("sliceHeight", n) } }
        SettingsInput { visible: Config.displayMode === "slices"; colors: settingsPanel.colors; label: "Visible items"; value: Config.wallpaperVisibleCount; min: 3; max: 30; onCommit: function(n) { settingsPanel._saveField("visibleCount", n) } }
        SettingsInput { visible: Config.displayMode === "slices"; colors: settingsPanel.colors; label: "Selected width"; value: Config.wallpaperExpandedWidth; min: 50; max: 1800; onCommit: function(n) { settingsPanel._saveField("expandedWidth", n) } }
        SettingsInput { visible: Config.displayMode === "hex"; colors: settingsPanel.colors; label: "Radius"; value: Config.hexRadius; min: 60; max: 300; onCommit: function(n) { settingsPanel._saveField("hexRadius", n) } }
        SettingsInput { visible: Config.displayMode === "hex"; colors: settingsPanel.colors; label: "Rows"; value: Config.hexRows; min: 1; max: 8; onCommit: function(n) { settingsPanel._saveField("hexRows", n) } }
        SettingsInput { visible: Config.displayMode === "hex"; colors: settingsPanel.colors; label: "Columns"; value: Config.hexCols; min: 3; max: 20; onCommit: function(n) { settingsPanel._saveField("hexCols", n) } }
        SettingsInput { visible: Config.displayMode === "hex"; colors: settingsPanel.colors; label: "Scroll step"; value: Config.hexScrollStep; min: 1; max: 10; onCommit: function(n) { settingsPanel._saveField("hexScrollStep", n) } }
        SettingsToggle { visible: Config.displayMode === "hex"; colors: settingsPanel.colors; label: "Arc layout"; checked: Config.hexArc; onToggle: function(v) { settingsPanel._saveField("hexArc", v) } }
        SettingsInput { visible: Config.displayMode === "hex" && Config.hexArc; colors: settingsPanel.colors; label: "Arc intensity (×10)"; value: Math.round(Config.hexArcIntensity * 10); min: 1; max: 30; onCommit: function(n) { settingsPanel._saveField("hexArcIntensity", n / 10) } }
        SettingsInput { visible: Config.displayMode === "wall"; colors: settingsPanel.colors; label: "Columns"; value: Config.gridColumns; min: 2; max: 12; onCommit: function(n) { settingsPanel._saveField("gridColumns", n) } }
        SettingsInput { visible: Config.displayMode === "wall"; colors: settingsPanel.colors; label: "Rows"; value: Config.gridRows; min: 1; max: 8; onCommit: function(n) { settingsPanel._saveField("gridRows", n) } }
        SettingsInput { visible: Config.displayMode === "wall"; colors: settingsPanel.colors; label: "Thumb width"; value: Config.gridThumbWidth; min: 100; max: 600; onCommit: function(n) { settingsPanel._saveField("gridThumbWidth", n) } }
        SettingsInput { visible: Config.displayMode === "wall"; colors: settingsPanel.colors; label: "Thumb height"; value: Config.gridThumbHeight; min: 50; max: 400; onCommit: function(n) { settingsPanel._saveField("gridThumbHeight", n) } }
      }

      Rectangle {
        width: 1; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.primary.r, settingsPanel.colors.primary.g, settingsPanel.colors.primary.b, 0.1) : Qt.rgba(1, 1, 1, 0.08)
      }

      Column {
        width: (parent.width - parent.spacing * 4 - 2) * 0.35
        spacing: 6

        Text {
          text: "GEOMETRY"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
          visible: Config.displayMode === "slices"
        }

        SettingsInput { visible: Config.displayMode === "slices"; colors: settingsPanel.colors; label: "Slice width"; value: Config.wallpaperSliceWidth; min: 50; max: 500; onCommit: function(n) { settingsPanel._saveField("sliceWidth", n) } }
        SettingsInput { visible: Config.displayMode === "slices"; colors: settingsPanel.colors; label: "Gap"; value: Config.wallpaperSliceSpacing; min: -500; max: 500; onCommit: function(n) { settingsPanel._saveField("sliceSpacing", n) } }
        SettingsInput { visible: Config.displayMode === "slices"; colors: settingsPanel.colors; label: "Skew"; value: Config.wallpaperSkewOffset; min: -500; max: 500; onCommit: function(n) { settingsPanel._saveField("skewOffset", n) } }
      }
    }

    Row {
      id: generalContent
      anchors.left: parent.left
      anchors.right: parent.right
      visible: settingsPanel.activeTab === "general"
      spacing: 12

      Column {
        width: (parent.width - 12) / 2
        spacing: 6

        Text {
          text: "GENERAL"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "Monitor"
          value: Config.mainMonitor
          placeholder: "e.g. DP-1"
          onCommit: function(v) { settingsPanel._saveConfigKey("monitor", v) }
        }

        SettingsCombo {
          colors: settingsPanel.colors
          label: "Color source"
          value: Config.colorSource
          model: ["ollama", "magick"]
          onSelect: function(v) { settingsPanel._saveConfigKey("colorSource", v) }
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Mute wallpaper audio"
          checked: Config.wallpaperMute
          onToggle: function(v) { settingsPanel._saveConfigKey("wallpaperMute", v) }
        }

        Item { width: 1; height: 6 }

        Text {
          text: "AUTO CHANGE"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Enable timed wallpaper change"
          checked: Config.wallpaperAutoChangeEnabled
          onToggle: function(v) { settingsPanel._saveField("autoChangeEnabled", v) }
        }

        SettingsCombo {
          colors: settingsPanel.colors
          label: "Mode"
          value: Config.wallpaperAutoChangeMode
          model: ["next", "random"]
          onSelect: function(v) { settingsPanel._saveField("autoChangeMode", v) }
        }

        SettingsInput {
          colors: settingsPanel.colors
          label: "Interval (minutes, min 1)"
          value: Config.wallpaperAutoChangeIntervalMinutes
          min: 1
          max: 2147483647
          onCommit: function(n) { settingsPanel._saveField("autoChangeIntervalMinutes", n) }
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "Filter bar background color"
          value: Config.wallpaperFilterBarBgColor
          placeholder: "empty = default, ex: #1e2430 or #cc1e2430"
          onCommit: function(v) { settingsPanel._saveField("filterBarBgColor", v.trim()) }
        }

        Text {
          width: parent.width
          text: "This changes the background of ALL/PIC/VID/WE and the rest of the filter chips. Clear the field to restore default theme color."
          font.family: Style.fontFamily; font.pixelSize: 10; font.letterSpacing: 0.2
          color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.75) : Qt.rgba(1, 1, 1, 0.45)
          wrapMode: Text.WordWrap
          lineHeight: 1.25
        }

      }

      Column {
        width: (parent.width - 12) / 2
        spacing: 6

        Text {
          text: "STEAM"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "API key"
          value: Config.steamApiKey
          secret: true
          placeholder: "Steam Web API key"
          onCommit: function(v) { settingsPanel._saveConfigKey("steam.apiKey", v) }
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "Username"
          value: Config.steamUsername
          placeholder: "Steam username"
          onCommit: function(v) { settingsPanel._saveConfigKey("steam.username", v) }
        }
      }
    }

    Row {
      id: ollamaContent
      anchors.left: parent.left
      anchors.right: parent.right
      visible: settingsPanel.activeTab === "ollama"
      spacing: 12

      onVisibleChanged: {
        if (visible) settingsPanel._fetchOllamaModels()
      }

      Column {
        width: (parent.width - 12) / 2
        spacing: 6

        Text {
          text: "CONNECTION"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "URL"
          value: Config.ollamaUrl
          placeholder: "http://localhost:11434"
          onCommit: function(v) {
            settingsPanel._saveConfigKey("ollama.url", v)
            settingsPanel._fetchOllamaModels()
          }
        }

        SettingsCombo {
          colors: settingsPanel.colors
          label: settingsPanel._ollamaModelsFetching ? "Model  󰔟" : (settingsPanel._ollamaModels.length === 0 ? "Model  (no models found)" : "Model")
          model: settingsPanel._ollamaModels
          value: Config.ollamaModel
          onSelect: function(v) { settingsPanel._saveConfigKey("ollama.model", v) }
        }

        FilterButton {
          colors: settingsPanel.colors
          icon: "󰑐"
          tooltip: "Refresh model list"
          onClicked: settingsPanel._fetchOllamaModels()
        }
      }

      Rectangle {
        width: 1; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.primary.r, settingsPanel.colors.primary.g, settingsPanel.colors.primary.b, 0.1) : Qt.rgba(1, 1, 1, 0.08)
      }

      Column {
        width: (parent.width - 12) / 2
        spacing: 6

        Text {
          text: "DATA"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        Item {
          width: parent.width; height: 28

          FilterButton {
            id: _deleteTagsBtn
            colors: settingsPanel.colors
            label: "DELETE ALL TAGS"
            skew: 8; height: 26
            hasActiveColor: true
            activeColor: "#c62828"
            isActive: _deleteTagsBtn.isHovered
            onClicked: _deleteConfirmPopup.open()
          }
        }

        Text {
          width: parent.width
          text: "Clears all Ollama-generated tags. The next analysis pass will re-tag everything with the current model."
          font.family: Style.fontFamily; font.pixelSize: 10; font.letterSpacing: 0.2
          color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceText.r, settingsPanel.colors.surfaceText.g, settingsPanel.colors.surfaceText.b, 0.45) : Qt.rgba(1, 1, 1, 0.35)
          wrapMode: Text.WordWrap
          lineHeight: 1.3
        }
      }
    }

    Row {
      id: pathsContent
      anchors.left: parent.left
      anchors.right: parent.right
      visible: settingsPanel.activeTab === "paths"
      spacing: 12

      Column {
        width: (parent.width - parent.spacing * 2 - 1) * 0.5
        spacing: 6

        Text {
          text: "DIRECTORIES"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "Wallpaper directory"
          value: Config.wallpaperDir
          placeholder: "~/Pictures/Wallpapers"
          onCommit: function(v) { settingsPanel._saveConfigKey("paths.wallpaper", v) }
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "Cache directory"
          value: Config.cacheDir
          placeholder: "~/.cache/skwd-wall"
          onCommit: function(v) { settingsPanel._saveConfigKey("paths.cache", v) }
        }
      }

      Rectangle {
        width: 1; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.primary.r, settingsPanel.colors.primary.g, settingsPanel.colors.primary.b, 0.1) : Qt.rgba(1, 1, 1, 0.08)
      }

      Column {
        width: (parent.width - parent.spacing * 2 - 1) * 0.5
        spacing: 6

        Text {
          text: "STEAM"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "Workshop directory"
          value: Config.weDir
          placeholder: "Steam Workshop content path"
          onCommit: function(v) { settingsPanel._saveConfigKey("paths.steamWorkshop", v) }
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "WE assets directory"
          value: Config.weAssetsDir
          placeholder: "Wallpaper Engine assets path"
          onCommit: function(v) { settingsPanel._saveConfigKey("paths.steamWeAssets", v) }
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "Steam directory"
          value: Config.steamDir
          placeholder: "Steam install path"
          onCommit: function(v) { settingsPanel._saveConfigKey("paths.steam", v) }
        }
      }
    }

    Row {
      id: wallhavenContent
      anchors.left: parent.left
      anchors.right: parent.right
      visible: settingsPanel.activeTab === "wallhaven"
      spacing: 12

      Column {
        width: (parent.width - parent.spacing * 2 - 1) * 0.5
        spacing: 6

        Text {
          text: "GRID"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsInput {
          colors: settingsPanel.colors
          label: "Columns"
          value: Config.wallhavenColumns
          min: 2; max: 12
          onCommit: function(n) { settingsPanel._saveField("wallhavenColumns", n) }
        }

        SettingsInput {
          colors: settingsPanel.colors
          label: "Rows"
          value: Config.wallhavenRows
          min: 1; max: 10
          onCommit: function(n) { settingsPanel._saveField("wallhavenRows", n) }
        }

        Text {
          text: "THUMBNAIL"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
          topPadding: 8
        }

        SettingsInput {
          colors: settingsPanel.colors
          label: "Width"
          value: Config.wallhavenThumbWidth
          min: 100; max: 600
          onCommit: function(n) { settingsPanel._saveField("wallhavenThumbWidth", n) }
        }

        SettingsInput {
          colors: settingsPanel.colors
          label: "Height"
          value: Config.wallhavenThumbHeight
          min: 60; max: 600
          onCommit: function(n) { settingsPanel._saveField("wallhavenThumbHeight", n) }
        }
      }

      Rectangle { width: 1; height: parent.height; color: Qt.rgba(1, 1, 1, 0.08) }

      Column {
        width: (parent.width - parent.spacing * 2 - 1) * 0.5
        spacing: 6

        Text {
          text: "API"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsTextInput {
          colors: settingsPanel.colors
          label: "API key"
          value: Config.wallhavenApiKey
          secret: true
          placeholder: "Wallhaven API key (for NSFW)"
          onCommit: function(v) { settingsPanel._saveConfigKey("wallhaven.apiKey", v) }
        }
      }
    }

    Row {
      id: featuresContent
      anchors.left: parent.left
      anchors.right: parent.right
      visible: settingsPanel.activeTab === "features"
      spacing: 12

      Column {
        width: (parent.width - parent.spacing * 2 - 1) * 0.5
        spacing: 8

        Text {
          text: "INTEGRATIONS"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Matugen (Colour theming)"
          checked: Config.matugenEnabled
          onToggle: function(v) { settingsPanel._saveConfigKey("features.matugen", v) }
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Ollama (Local LLM colour & tagging)"
          checked: Config.ollamaEnabled
          onToggle: function(v) { settingsPanel._saveConfigKey("features.ollama", v) }
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Steam Workshop browser"
          checked: Config.steamEnabled
          onToggle: function(v) { settingsPanel._saveConfigKey("features.steam", v) }
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Wallhaven browser"
          checked: Config.wallhavenEnabled
          onToggle: function(v) { settingsPanel._saveConfigKey("features.wallhaven", v) }
        }
      }

      Rectangle {
        width: 1; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.primary.r, settingsPanel.colors.primary.g, settingsPanel.colors.primary.b, 0.1) : Qt.rgba(1, 1, 1, 0.08)
      }

      Column {
        width: (parent.width - parent.spacing * 2 - 1) * 0.5
        spacing: 8

        Text {
          text: "OTHER"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Show colour dots"
          checked: Config.wallpaperColorDots
          onToggle: function(v) { settingsPanel._saveConfigKey("components.wallpaperSelector.showColorDots", v) }
        }
      }
    }

    Row {
      id: performanceContent
      anchors.left: parent.left
      anchors.right: parent.right
      visible: settingsPanel.activeTab === "performance"
      spacing: 12

      Column {
        width: (parent.width - parent.spacing * 4 - 2) / 3
        spacing: 6

        Text {
          text: "IMAGE OPTIMIZATION"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        Text {
          width: parent.width
          text: "Converts PNG, JPEG, and GIF images to WebP format. Smaller file sizes with no visible quality loss. Steam Workshop assets are never modified."
          font.family: Style.fontFamily; font.pixelSize: 11; font.letterSpacing: 0.2
          color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.8) : Qt.rgba(1, 1, 1, 0.5)
          wrapMode: Text.WordWrap
          lineHeight: 1.3
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Auto-optimize new images"
          checked: Config.autoOptimizeImages
          onToggle: function(v) { settingsPanel._saveConfigKey("performance.autoOptimizeImages", v) }
        }

        SettingsCombo {
          colors: settingsPanel.colors
          label: "Quality"
          model: ["light", "balanced", "quality"]
          value: Config.imageOptimizePreset
          onSelect: function(v) { settingsPanel._saveConfigKey("performance.imageOptimizePreset", v) }
        }

        Repeater {
          model: [
            { key: "light",    desc: "Q 82 · max compression" },
            { key: "balanced", desc: "Q 88 · good trade-off" },
            { key: "quality",  desc: "Q 94 · visually lossless" }
          ]
          Text {
            text: (Config.imageOptimizePreset === modelData.key ? "▸ " : "  ") + modelData.key.toUpperCase() + ":  " + modelData.desc
            font.family: Style.fontFamily; font.pixelSize: 10; font.letterSpacing: 0.2
            color: Config.imageOptimizePreset === modelData.key
              ? (settingsPanel.colors ? settingsPanel.colors.primary : Style.fallbackAccent)
              : (settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.7) : Qt.rgba(1, 1, 1, 0.4))
          }
        }

        SettingsCombo {
          colors: settingsPanel.colors
          label: "Max resolution"
          model: ["1080p", "2k", "4k"]
          value: Config.imageOptimizeResolution
          onSelect: function(v) { settingsPanel._saveConfigKey("performance.imageOptimizeResolution", v) }
        }

        Text {
          width: parent.width
          text: "Images above the cap are downscaled. Smaller images are never upscaled."
          font.family: Style.fontFamily; font.pixelSize: 11; font.letterSpacing: 0.2
          color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.8) : Qt.rgba(1, 1, 1, 0.5)
          wrapMode: Text.WordWrap
          lineHeight: 1.3
        }

        Item { width: 1; height: 2 }

        Row {
          spacing: 8

          FilterButton {
            colors: settingsPanel.colors
            label: ImageOptimizeService.running ? "CANCEL" : "OPTIMIZE ALL"
            skew: 8
            height: 28
            isActive: ImageOptimizeService.running
            onClicked: {
              if (ImageOptimizeService.running) ImageOptimizeService.cancel()
              else _optimizeConfirmPopup.open()
            }
          }

          Text {
            anchors.verticalCenter: parent.verticalCenter
            visible: !ImageOptimizeService.running && settingsPanel._lastOptimizeResult !== ""
            text: settingsPanel._lastOptimizeResult
            font.family: Style.fontFamily; font.pixelSize: 10; font.letterSpacing: 0.2
            color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.8) : Qt.rgba(1, 1, 1, 0.5)
          }
        }
      }

      Rectangle {
        width: 1; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.primary.r, settingsPanel.colors.primary.g, settingsPanel.colors.primary.b, 0.1) : Qt.rgba(1, 1, 1, 0.08)
      }

      Item {
        width: (parent.width - parent.spacing * 4 - 2) / 3
        height: _videoOptCol.implicitHeight

        Column {
          id: _videoOptCol
          width: parent.width
          spacing: 6
          opacity: 0.35
          enabled: false

          Text {
            text: "VIDEO OPTIMIZATION  ·  WIP"
            font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
            color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
          }

          Text {
            width: parent.width
            text: "Re-encodes video wallpapers to HEVC (H.265) for significantly smaller sizes. This feature is currently under development."
            font.family: Style.fontFamily; font.pixelSize: 11; font.letterSpacing: 0.2
            color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.8) : Qt.rgba(1, 1, 1, 0.5)
            wrapMode: Text.WordWrap
            lineHeight: 1.3
          }

          SettingsToggle {
            colors: settingsPanel.colors
            label: "Auto-convert new videos"
            checked: false
          }

          SettingsCombo {
            colors: settingsPanel.colors
            label: "Quality"
            model: ["light", "balanced", "quality"]
            value: Config.videoConvertPreset
          }

          Repeater {
            model: [
              { key: "light",    desc: "CRF 28 · 6 Mbps" },
              { key: "balanced", desc: "CRF 26 · 10 Mbps" },
              { key: "quality",  desc: "CRF 23 · 16 Mbps" }
            ]
            Text {
              text: (Config.videoConvertPreset === modelData.key ? "▸ " : "  ") + modelData.key.toUpperCase() + ":  " + modelData.desc
              font.family: Style.fontFamily; font.pixelSize: 10; font.letterSpacing: 0.2
              color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.7) : Qt.rgba(1, 1, 1, 0.4)
            }
          }

          SettingsCombo {
            colors: settingsPanel.colors
            label: "Max resolution"
            model: ["1080p", "2k", "4k"]
            value: Config.videoConvertResolution
          }

          Item { width: 1; height: 2 }

          Row {
            spacing: 8

            FilterButton {
              colors: settingsPanel.colors
              label: "OPTIMIZE ALL"
              skew: 8
              height: 28
            }
          }
        }
      }

      Rectangle {
        width: 1; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.primary.r, settingsPanel.colors.primary.g, settingsPanel.colors.primary.b, 0.1) : Qt.rgba(1, 1, 1, 0.08)
      }

      Column {
        width: (parent.width - parent.spacing * 4 - 2) / 3
        spacing: 6

        Text {
          text: "VIDEO PREVIEWS"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        Text {
          width: parent.width
          text: "Play animated thumbnails when hovering over video wallpapers."
          font.family: Style.fontFamily; font.pixelSize: 11; font.letterSpacing: 0.2
          color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.8) : Qt.rgba(1, 1, 1, 0.5)
          wrapMode: Text.WordWrap
          lineHeight: 1.3
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Video previews"
          checked: Config.videoPreviewEnabled
          onToggle: function(v) { settingsPanel._saveConfigKey("features.videoPreview", v) }
        }

        Item { width: 1; height: 8 }

        Text {
          text: "TRASH"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        Text {
          width: parent.width
          text: "Originals are moved to trash before optimization, so you can recover them if needed."
          font.family: Style.fontFamily; font.pixelSize: 11; font.letterSpacing: 0.2
          color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceVariantText.r, settingsPanel.colors.surfaceVariantText.g, settingsPanel.colors.surfaceVariantText.b, 0.8) : Qt.rgba(1, 1, 1, 0.5)
          wrapMode: Text.WordWrap
          lineHeight: 1.3
        }

        Item { width: 1; height: 2 }

        Text {
          text: "IMAGES"
          font.family: Style.fontFamily; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 1.2
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        SettingsInput {
          colors: settingsPanel.colors
          label: "Retention (days)"
          value: Config.imageTrashDays
          min: 1; max: 365
          onCommit: function(v) { settingsPanel._saveConfigKey("performance.imageTrashDays", v) }
        }

        SettingsToggle {
          colors: settingsPanel.colors
          label: "Auto-delete after retention"
          checked: Config.autoDeleteImageTrash
          onToggle: function(v) { settingsPanel._saveConfigKey("performance.autoDeleteImageTrash", v) }
        }

        Item { width: 1; height: 4 }

        Item {
          width: parent.width
          height: _videoTrashCol.implicitHeight
          opacity: 0.35
          enabled: false

          Column {
            id: _videoTrashCol
            width: parent.width
            spacing: 6

            Text {
              text: "VIDEOS  ·  WIP"
              font.family: Style.fontFamily; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 1.2
              color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
            }

            SettingsInput {
              colors: settingsPanel.colors
              label: "Retention (days)"
              value: Config.videoTrashDays
              min: 1; max: 365
            }

            SettingsToggle {
              colors: settingsPanel.colors
              label: "Auto-delete after retention"
              checked: false
            }
          }
        }
      }
    }

    Row {
      id: keybindsContent
      anchors.left: parent.left
      anchors.right: parent.right
      visible: settingsPanel.activeTab === "keybinds"
      spacing: 12

      Column {
        width: (parent.width - parent.spacing * 2 - 1) * 0.5
        spacing: 6

        Text {
          text: "NAVIGATION"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        Repeater {
          model: [
            { key: "← / →",         action: "Navigate items" },
            { key: "↑ / ↓",         action: "Navigate rows (hex/grid)" },
            { key: "Enter",          action: "Apply wallpaper" },
            { key: "Escape",         action: "Close panel / overlay" },
            { key: "Right-click",    action: "Flip card (details)" },
            { key: "Scroll",         action: "Browse wallpapers" }
          ]
          Item {
            width: parent.width; height: 20
            Text {
              anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
              text: modelData.key
              font.family: Style.fontFamily; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 0.3
              color: settingsPanel.colors ? settingsPanel.colors.primary : Style.fallbackAccent
            }
            Text {
              anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
              text: modelData.action
              font.family: Style.fontFamily; font.pixelSize: 11
              color: settingsPanel.colors ? settingsPanel.colors.surfaceText : Qt.rgba(1, 1, 1, 0.7)
            }
          }
        }
      }

      Rectangle {
        width: 1; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.primary.r, settingsPanel.colors.primary.g, settingsPanel.colors.primary.b, 0.1) : Qt.rgba(1, 1, 1, 0.08)
      }

      Column {
        width: (parent.width - parent.spacing * 2 - 1) * 0.5
        spacing: 6

        Text {
          text: "FILTERS & TAGS"
          font.family: Style.fontFamily; font.pixelSize: 13; font.weight: Font.Bold; font.letterSpacing: 1.5
          color: settingsPanel.colors ? settingsPanel.colors.tertiary : Qt.rgba(1, 1, 1, 0.5)
        }

        Repeater {
          model: [
            { key: "Shift + ← / →",  action: "Cycle colour filters" },
            { key: "Shift + ↓",      action: "Toggle tag cloud" },
            { key: "Tab",            action: "Auto-complete tag" },
            { key: "Enter",          action: "Add tag (in tag input)" },
            { key: "Escape",         action: "Clear search / close" }
          ]
          Item {
            width: parent.width; height: 20
            Text {
              anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
              text: modelData.key
              font.family: Style.fontFamily; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 0.3
              color: settingsPanel.colors ? settingsPanel.colors.primary : Style.fallbackAccent
            }
            Text {
              anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
              text: modelData.action
              font.family: Style.fontFamily; font.pixelSize: 11
              color: settingsPanel.colors ? settingsPanel.colors.surfaceText : Qt.rgba(1, 1, 1, 0.7)
            }
          }
        }
      }
    }
  }

  Rectangle {
    id: _deleteConfirmPopup
    visible: false
    anchors.fill: parent
    z: 200
    color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surface.r, settingsPanel.colors.surface.g, settingsPanel.colors.surface.b, 0.97) : Qt.rgba(0.08, 0.08, 0.12, 0.97)
    radius: 8

    function open() { _deleteConfirmInput.text = ""; visible = true; _deleteConfirmInput.forceActiveFocus() }
    function close() { visible = false }

    MouseArea { anchors.fill: parent; onClicked: function(mouse) { mouse.accepted = true } }

    Column {
      anchors.centerIn: parent
      spacing: 12
      width: parent.width * 0.7

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "\u{f0027}"
        font.family: Style.fontFamilyNerdIcons; font.pixelSize: 28
        color: "#ef5350"
      }

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "DELETE ALL TAGS?"
        font.family: Style.fontFamily; font.pixelSize: 14; font.weight: Font.Bold; font.letterSpacing: 1.5
        color: settingsPanel.colors ? settingsPanel.colors.surfaceText : "#fff"
      }

      Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: "This will erase every Ollama-generated tag and re-analyse all wallpapers with the current model. This cannot be undone."
        font.family: Style.fontFamily; font.pixelSize: 11; font.letterSpacing: 0.2
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceText.r, settingsPanel.colors.surfaceText.g, settingsPanel.colors.surfaceText.b, 0.6) : Qt.rgba(1, 1, 1, 0.5)
        wrapMode: Text.WordWrap
        lineHeight: 1.3
      }

      Item { width: 1; height: 2 }

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: 'Type "delete" to confirm'
        font.family: Style.fontFamily; font.pixelSize: 11
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceText.r, settingsPanel.colors.surfaceText.g, settingsPanel.colors.surfaceText.b, 0.5) : Qt.rgba(1, 1, 1, 0.4)
      }

      Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        width: 180; height: 30; radius: 15
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surface.r, settingsPanel.colors.surface.g, settingsPanel.colors.surface.b, 0.5) : Qt.rgba(0, 0, 0, 0.3)
        border.width: _deleteConfirmInput.activeFocus ? 1 : 0
        border.color: "#ef5350"

        TextInput {
          id: _deleteConfirmInput
          anchors.fill: parent
          anchors.leftMargin: 14; anchors.rightMargin: 14
          verticalAlignment: TextInput.AlignVCenter
          horizontalAlignment: TextInput.AlignHCenter
          font.family: Style.fontFamily; font.pixelSize: 12; font.letterSpacing: 0.5
          color: settingsPanel.colors ? settingsPanel.colors.surfaceText : "#fff"
          clip: true
          Keys.onEscapePressed: _deleteConfirmPopup.close()
          Keys.onReturnPressed: {
            if (_deleteConfirmInput.text.toLowerCase().trim() === "delete") {
              WallpaperAnalysisService.regenerate()
              _deleteConfirmPopup.close()
            }
          }
        }
      }

      Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 8

        FilterButton {
          colors: settingsPanel.colors
          label: "CANCEL"
          skew: 8; height: 26
          onClicked: _deleteConfirmPopup.close()
        }

        FilterButton {
          id: _confirmDeleteBtn
          property bool canConfirm: _deleteConfirmInput.text.toLowerCase().trim() === "delete"
          colors: settingsPanel.colors
          label: "CONFIRM"
          skew: 8; height: 26
          hasActiveColor: true
          activeColor: canConfirm ? "#c62828" : Qt.rgba(0.5, 0.5, 0.5, 0.3)
          isActive: canConfirm
          activeOpacity: canConfirm ? 1.0 : 0.4
          onClicked: {
            if (canConfirm) {
              WallpaperAnalysisService.regenerate()
              _deleteConfirmPopup.close()
            }
          }
        }
      }
    }
  }

  Rectangle {
    id: _optimizeConfirmPopup
    visible: false
    anchors.fill: parent
    z: 201
    color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surface.r, settingsPanel.colors.surface.g, settingsPanel.colors.surface.b, 0.97) : Qt.rgba(0.08, 0.08, 0.12, 0.97)
    radius: 8

    function open() { visible = true }
    function close() { visible = false }

    MouseArea { anchors.fill: parent; onClicked: function(mouse) { mouse.accepted = true } }

    Column {
      anchors.centerIn: parent
      spacing: 12
      width: parent.width * 0.7

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "\u{f03e}"
        font.family: Style.fontFamilyNerdIcons; font.pixelSize: 28
        color: settingsPanel.colors ? settingsPanel.colors.primary : Style.fallbackAccent
      }

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "OPTIMIZE ALL IMAGES?"
        font.family: Style.fontFamily; font.pixelSize: 14; font.weight: Font.Bold; font.letterSpacing: 1.5
        color: settingsPanel.colors ? settingsPanel.colors.surfaceText : "#fff"
      }

      Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: {
          var p = ImageOptimizeService.presets[Config.imageOptimizePreset]
          var r = ImageOptimizeService.resolutions[Config.imageOptimizeResolution]
          var fmts = p ? p.formats.join(", ").toUpperCase() : "?"
          return "This will convert " + fmts + " images to WebP using the " +
            Config.imageOptimizePreset.toUpperCase() + " preset (quality " + (p ? p.quality : "?") +
            ", max " + (r ? r.maxW + "x" + r.maxH : "?") +
            "). Originals are moved to trash. Already optimized files will be skipped."
        }
        font.family: Style.fontFamily; font.pixelSize: 11; font.letterSpacing: 0.2
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceText.r, settingsPanel.colors.surfaceText.g, settingsPanel.colors.surfaceText.b, 0.6) : Qt.rgba(1, 1, 1, 0.5)
        wrapMode: Text.WordWrap
        lineHeight: 1.3
      }

      Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: "Only images in your wallpaper directory are processed — Steam Workshop assets are left untouched."
        font.family: Style.fontFamily; font.pixelSize: 10; font.letterSpacing: 0.2
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceText.r, settingsPanel.colors.surfaceText.g, settingsPanel.colors.surfaceText.b, 0.4) : Qt.rgba(1, 1, 1, 0.35)
        wrapMode: Text.WordWrap
        lineHeight: 1.3
      }

      Item { width: 1; height: 4 }

      Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 8

        FilterButton {
          colors: settingsPanel.colors
          label: "CANCEL"
          skew: 8; height: 26
          onClicked: _optimizeConfirmPopup.close()
        }

        FilterButton {
          colors: settingsPanel.colors
          label: "OPTIMIZE"
          skew: 8; height: 26
          isActive: true
          onClicked: {
            _optimizeConfirmPopup.close()
            ImageOptimizeService.optimize(Config.imageOptimizePreset, Config.imageOptimizeResolution)
          }
        }
      }
    }
  }

  Rectangle {
    id: _convertConfirmPopup
    visible: false
    anchors.fill: parent
    z: 200
    color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surface.r, settingsPanel.colors.surface.g, settingsPanel.colors.surface.b, 0.97) : Qt.rgba(0.08, 0.08, 0.12, 0.97)
    radius: 8

    function open() { visible = true }
    function close() { visible = false }

    MouseArea { anchors.fill: parent; onClicked: function(mouse) { mouse.accepted = true } }

    Column {
      anchors.centerIn: parent
      spacing: 12
      width: parent.width * 0.7

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "\u{f03d}"
        font.family: Style.fontFamilyNerdIcons; font.pixelSize: 28
        color: settingsPanel.colors ? settingsPanel.colors.primary : Style.fallbackAccent
      }

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "OPTIMIZE ALL VIDEOS?"
        font.family: Style.fontFamily; font.pixelSize: 14; font.weight: Font.Bold; font.letterSpacing: 1.5
        color: settingsPanel.colors ? settingsPanel.colors.surfaceText : "#fff"
      }

      Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: {
          var p = VideoConvertService.presets[Config.videoConvertPreset]
          var r = VideoConvertService.resolutions[Config.videoConvertResolution]
          return "This will convert all video wallpapers to HEVC (H.265) using the " +
            Config.videoConvertPreset.toUpperCase() + " preset (CRF " + (p ? p.crf : "?") +
            ", max " + (p ? p.maxrate : "?") + ", " + (r ? r.maxW + "x" + r.maxH : "?") +
            "). Originals are moved to trash. Already converted files will be skipped."
        }
        font.family: Style.fontFamily; font.pixelSize: 11; font.letterSpacing: 0.2
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceText.r, settingsPanel.colors.surfaceText.g, settingsPanel.colors.surfaceText.b, 0.6) : Qt.rgba(1, 1, 1, 0.5)
        wrapMode: Text.WordWrap
        lineHeight: 1.3
      }

      Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: "This may take a while depending on the number and size of videos."
        font.family: Style.fontFamily; font.pixelSize: 10; font.letterSpacing: 0.2
        color: settingsPanel.colors ? Qt.rgba(settingsPanel.colors.surfaceText.r, settingsPanel.colors.surfaceText.g, settingsPanel.colors.surfaceText.b, 0.4) : Qt.rgba(1, 1, 1, 0.35)
        wrapMode: Text.WordWrap
        lineHeight: 1.3
      }

      Item { width: 1; height: 4 }

      Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 8

        FilterButton {
          colors: settingsPanel.colors
          label: "CANCEL"
          skew: 8; height: 26
          onClicked: _convertConfirmPopup.close()
        }

        FilterButton {
          colors: settingsPanel.colors
          label: "CONVERT"
          skew: 8; height: 26
          isActive: false
          enabled: false
          opacity: 0.35
        }
      }
    }
  }
}
