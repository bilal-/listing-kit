# Run only by the fastlane gem matrix in CI. No store credentials or network client.
require "json"
require "open3"
require "pathname"
require "fastlane"
require "deliver"
require "deliver/loader"
require "supply"
require "supply/uploader"

cases, result = Open3.capture2("python3", "-IB", File.join(__dir__, "fastlane_cases.py"))
abort "Could not build listing-kit contract inputs" unless result.success?
cases = JSON.parse(cases)
{ "deliver" => Deliver::Options, "supply" => Supply::Options }.each do |action, options|
  missing = cases.fetch("options").fetch(action) - options.available_options.map { |opt| opt.key.to_s }
  abort "#{action} no longer accepts #{missing.join(', ')}" unless missing.empty?
end

root = Pathname(__dir__).join("../../examples/expo-recipe-box/fastlane").realpath
screens = root.join("screenshots")
loaded = Deliver::Loader.load_app_screenshots(screens.to_s, false)
actual = loaded.map do |shot|
  display = shot.respond_to?(:display_type) ? shot.display_type : shot.screen_size
  [Pathname(shot.path).relative_path_from(screens).to_s, display]
end
expected = cases.fetch("apple").to_a
abort "Deliver loader mismatch: #{actual.inspect}, expected #{expected.inspect}" unless actual.sort == expected.sort

# UNVERIFIED until the pinned CI job runs: Supply's private Ruby method signatures
# and the AppScreenshot reader above. A change fails this test before any login.
class ListingDouble
  attr_accessor :title, :short_description, :full_description, :video
  attr_reader :saved
  def save
    @saved = true
  end
end

class ClientDouble
  attr_reader :uploads, :clears, :listing
  def initialize
    @uploads = []
    @clears = []
    @listing = ListingDouble.new
  end

  def listing_for_language(language:)
    raise language unless language == "en-US"
    listing
  end

  def clear_screenshots(image_type:, language:)
    clears << [language, image_type]
  end

  def upload_image(image_path:, image_type:, language:)
    uploads << [language, image_type, File.realpath(image_path)]
  end
end

metadata = root.join("metadata/android")
Supply.config = FastlaneCore::Configuration.create(Supply::Options.available_options, metadata_path: metadata.to_s)
client = ClientDouble.new
uploader = Supply::Uploader.new
uploader.define_singleton_method(:client) { client }
# Pass the in-memory listing when the helper accepts it directly.
method = uploader.method(:upload_metadata)
arguments = method.parameters.map { |_, name| {language: "en-US", listing: client.listing}.fetch(name) }
method.call(*arguments)
%w[title short_description full_description].each do |key|
  abort "Supply missed #{key}" unless client.listing.public_send(key) == metadata.join("en-US", "#{key}.txt").read
end
abort "Supply did not save the listing" unless client.listing.saved
uploader.send(:upload_screenshots, "en-US")
expected = Dir[metadata.join("en-US/images/*Screenshots/*").to_s].sort.map do |path|
  ["en-US", File.basename(File.dirname(path)), path]
end
abort "Supply screenshot lookup/order changed" unless client.uploads == expected
abort "Supply replacement scope changed" unless client.clears == expected.map { |loc, type, _| [loc, type] }.uniq
puts "Fastlane loader, listing fields, replacement scope and option contracts passed"
