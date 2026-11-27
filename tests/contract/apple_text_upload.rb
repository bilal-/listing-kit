# Load the installed gem, but give the writer only these in-memory API objects.
require "fastlane"
require "spaceship"
require "tmpdir"
require "stringio"
require "fileutils"
require "minitest/autorun"
require_relative "../../skills/listing-kit/scripts/fastlane/apple_text_upload"

class AppleTextContract < Minitest::Test
  def setup
    @dir = Dir.mktmpdir
    @writes = []
    @api = Spaceship::ConnectAPI
    @unexpected = []
    @version = strict_double
    @app = strict_double
    info = strict_double
    local_info = resource(:info)
    local_version = resource(:version)
    @version.define_singleton_method(:get_app_store_version_localizations) { [local_version] }
    @infos = [local_info]
    infos = @infos
    info.define_singleton_method(:get_app_info_localizations) { infos }
    @app.define_singleton_method(:fetch_edit_app_info) { info }
    version = @version
    @app.define_singleton_method(:get_edit_app_store_version) do |platform:, includes:|
      raise unless platform == Spaceship::ConnectAPI::Platform::IOS
      raise unless includes == Spaceship::ConnectAPI::AppStoreVersion::ESSENTIAL_INCLUDES + ",appClipDefaultExperience"
      version
    end
    # Strict doubles expose no creation, release, category, rating, review,
    # attachment or version write methods. Every unexpected call fails the test.
  end

  def teardown
    FileUtils.remove_entry(@dir)
    assert_empty @unexpected
  end

  def strict_double
    unexpected = @unexpected
    obj = Object.new
    obj.define_singleton_method(:method_missing) do |method, *|
      unexpected << method
      raise NoMethodError, method.to_s
    end
    obj
  end

  def resource(group)
    writes = @writes
    client = strict_double
    # Exercise the installed model's attribute mapping and PATCH signature,
    # while allowing no HTTP client or other write operation.
    if group == :info
      model = @api::AppInfoLocalization.new("info-localization", {})
      client.define_singleton_method(:patch_app_info_localization) do |app_info_localization_id:, attributes:|
        raise unless app_info_localization_id == "info-localization"
        writes << [group, attributes]
      end
    else
      model = @api::AppStoreVersionLocalization.new("version-localization", {})
      client.define_singleton_method(:patch_app_store_version_localization) do |app_store_version_localization_id:, attributes:|
        raise unless app_store_version_localization_id == "version-localization"
        writes << [group, attributes]
      end
    end
    obj = strict_double
    obj.define_singleton_method(:locale) { "en-US" }
    obj.define_singleton_method(:update) { |attributes:| model.update(client: client, attributes: attributes) }
    obj
  end

  def stage(path, value)
    file = File.join(@dir, path)
    FileUtils.mkdir_p(File.dirname(file))
    File.write(file, value)
  end

  def upload
    token = Object.new
    loader = ->(hash:, filepath:) { raise unless hash.nil? && filepath == "private-key-path"; token }
    finder = ->(identifier) { raise unless identifier == "test.app"; @app }
    @api::Token.stub(:from, loader) do
      @api.stub(:token=, ->(actual) { raise unless actual.equal?(token) }) do
        @api::App.stub(:find, finder) do
          output = StringIO.new
          result = AppleTextUpload.run("test.app", "private-key-path", @dir, output)
          return result, output.string
        end
      end
    end
  end

  def test_exact_localized_updates
    groups = {info: %w[name subtitle privacy_url], version: %w[description keywords promotional_text release_notes support_url marketing_url]}
    mapped = {"release_notes" => "whatsNew", "privacy_url" => "privacyPolicyUrl",
              "marketing_url" => "marketingUrl", "support_url" => "supportUrl", "promotional_text" => "promotionalText"}
    expected = {}
    groups.each do |group, fields|
      expected[group] = fields.to_h do |field|
        stage("en-US/#{field}.txt", "private #{field}\n")
        [mapped.fetch(field, field), "private #{field}"]
      end
    end
    status, output = upload
    assert_equal 0, status
    assert_equal expected, @writes.to_h
    assert_equal 2, @writes.size
    groups.values.flatten.each { |field| assert_includes output, "en-US #{field}" }
    refute_includes output, "private"
  end

  def test_copyright_is_the_only_version_attribute
    stage("copyright.txt", "private copyright")
    writes = @writes
    @version.define_singleton_method(:update) { |attributes:| writes << attributes }
    assert_equal 0, upload.first
    assert_equal [{"copyright" => "private copyright"}], @writes
  end

  def test_missing_locale_before_any_write
    # A locale may exist on app info but still be absent from this version.
    french_info = resource(:info)
    french_info.define_singleton_method(:locale) { "fr-FR" }
    @infos << french_info
    stage("copyright.txt", "private copyright")
    stage("en-US/subtitle.txt", "private subtitle")
    stage("fr-FR/name.txt", "private name")
    status, output = upload
    refute_equal 0, status
    assert_match(/fr-FR/, output)
    assert_match(/0 fields written/, output)
    assert_empty @writes
  end

  def test_missing_info_locale_before_any_write
    stage("en-US/description.txt", "private description")
    stage("en-US/name.txt", "private name")
    @infos.clear
    status, output = upload
    refute_equal 0, status
    assert_match(/missing locale en-US/, output)
    assert_match(/0 fields written/, output)
    assert_empty @writes
  end

  def test_empty_value_before_any_write
    stage("en-US/name.txt", "private name")
    stage("en-US/description.txt", " \n")
    status, output = upload
    refute_equal 0, status
    assert_match(/empty/i, output)
    assert_match(/0 fields written/, output)
    assert_empty @writes
  end

  def test_partial_failure_is_counted_and_redacted
    stage("en-US/name.txt", "private name")
    stage("en-US/description.txt", "private description")
    @writes.define_singleton_method(:<<) do |entry|
      raise "private API body" unless empty?
      super(entry)
    end
    status, output = upload
    refute_equal 0, status
    assert_match(/1 fields? written/, output)
    refute_includes output, "private"
  end
end
