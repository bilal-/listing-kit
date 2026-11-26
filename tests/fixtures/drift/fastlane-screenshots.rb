# Hand-written fixture of display type to pixel dimensions.
sizes = {
  DisplayType::IOS_65 => [
    [1284, 2778], [2778, 1284]
  ],
  DisplayType::APPLE_TV => [[1920, 1080]],
  # DisplayType::UNUSED => [[123, 456]],
}
lookup = { [1024, 768] => DisplayType::IPAD }
