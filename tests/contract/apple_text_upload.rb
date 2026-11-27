# Load the installed gem, but give the writer only these in-memory API objects.
require "fastlane"
require "spaceship"
require "tmpdir"
require "openssl"
require "json"
require "stringio"
require "fileutils"
require "minitest/autorun"
require_relative "../../skills/listing-kit/scripts/fastlane/apple_text_upload"

class AppleTextContract < Minitest::Test
  def setup
    @staging = File.realpath(Dir.mktmpdir)
    @dir = File.join(@staging, "metadata")
    Dir.mkdir(@dir)
    @secret = "ab" * 32
    @pins = {"id" => "version-id", "appInfoId" => "info-id",
             "localizations" => [["en-US", "version-localization", "info-localization"]]}
    @previous_secret = ENV["LK_APPLE_WRITE_SECRET"]
    @previous_override = ENV["LK_PUBLISH_UNVERIFIED"]
    ENV["LK_PUBLISH_UNVERIFIED"] = "apple:test.app"
    @writes = []
    @api = Spaceship::ConnectAPI
    @unexpected = []
    @model = @api::AppStoreVersion.new("version-id", {
      "versionString" => "1.2.3", "appVersionState" => "PREPARE_FOR_SUBMISSION"
    })
    @version = strict_double
    model = @model
    %i[id version_string app_version_state].each do |attribute|
      @version.define_singleton_method(attribute) { model.public_send(attribute) }
    end
    @app = strict_double
    @app.define_singleton_method(:bundle_id) { "test.app" }
    @info = info = @api::AppInfo.new("info-id", {"state" => "DEVELOPER_REJECTED"})
    local_info = resource(:info)
    @local_version = local_version = resource(:version)
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
    @app.define_singleton_method(:get_latest_app_store_version) { |platform:| version }
    # Strict doubles expose no creation, release, category, rating, review,
    # attachment or version write methods. Every unexpected call fails the test.
  end

  def teardown
    ENV["LK_APPLE_WRITE_SECRET"] = @previous_secret
    ENV["LK_PUBLISH_UNVERIFIED"] = @previous_override
    FileUtils.remove_entry(@staging)
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
    obj.define_singleton_method(:id) { model.id }
    obj.define_singleton_method(:locale) { "en-US" }
    obj.define_singleton_method(:update) { |attributes:| model.update(client: client, attributes: attributes) }
    obj
  end

  def stage(path, value)
    file = File.join(@dir, path)
    FileUtils.mkdir_p(File.dirname(file))
    File.write(file, value)
  end

  def approved_args
    files = Dir.glob(File.join(@dir, "**/*.txt")).sort.map do |path|
      [path.delete_prefix(@staging + "/"), Digest::SHA256.file(path).hexdigest]
    end
    message = JSON.generate(["test.app", @pins["id"], @pins["appInfoId"], @pins["localizations"], files])
    token = OpenSSL::HMAC.hexdigest("SHA256", @secret, message)
    pins_path = File.join(@staging, "apple-target.json")
    File.write(pins_path, JSON.generate(@pins))
    ["write", "test.app", "private-key-path", @dir, pins_path, token]
  end

  def upload(args = approved_args, approval_secret: @secret)
    token = Object.new
    loader = ->(hash:, filepath:) { raise unless hash.nil? && filepath == "private-key-path"; token }
    finder = ->(identifier) { raise unless %w[test.app other.app].include?(identifier); @app }
    @api::Token.stub(:from, loader) do
      @api.stub(:token=, ->(actual) { raise unless actual.equal?(token) }) do
        @api::App.stub(:find, finder) do
          output = StringIO.new
          ENV["LK_APPLE_WRITE_SECRET"] = approval_secret
          result = AppleTextUpload.run(args, output)
          return result, output.string
        end
      end
    end
  end

  def test_describe_is_read_only_and_needs_no_approval
    status, output = upload(%w[describe test.app private-key-path], approval_secret: nil)
    assert_equal 0, status
    assert_equal ["version 1.2.3 version-id PREPARE_FOR_SUBMISSION", "appInfo info-id DEVELOPER_REJECTED",
                  "locale en-US version-localization info-localization"], output.lines.map(&:chomp)
    assert_empty @writes
  end

  def test_describe_preserves_one_sided_localizations
    @infos.first.define_singleton_method(:locale) { "fr-FR" }
    status, output = upload(%w[describe test.app private-key-path], approval_secret: nil)
    assert_equal 0, status
    assert_equal ["locale en-US version-localization .", "locale fr-FR . info-localization"], output.lines.last(2).map(&:chomp)
    assert_empty @writes
  end

  def test_describe_refuses_to_compare_a_different_download_version
    latest = Struct.new(:id).new("other-id")
    @app.define_singleton_method(:get_latest_app_store_version) { |platform:| latest }
    status, output = upload(%w[describe test.app private-key-path], approval_secret: nil)
    refute_equal 0, status
    assert_includes output, "download version differs from editable version"
    assert_empty @writes
  end

  def test_successor_refused_before_writing
    stage("en-US/name.txt", "private name")
    @pins["id"] = "old-id"
    status, output = upload
    refute_equal 0, status
    assert_includes output, "editable version changed"
    assert_empty @writes
  end

  def test_replaced_resource_refused_before_any_patch
    stage("copyright.txt", "private copyright")
    stage("en-US/name.txt", "private name")
    stage("en-US/description.txt", "private description")
    [@info, @local_version, @infos.first].each do |resource|
      args = approved_args
      resource.stub(:id, "replacement") do
        status, output = upload(args)
        refute_equal 0, status
        assert_includes output, "0 fields written"
        refute_includes output, "replacement"
        assert_empty @writes
      end
    end
  end

  def test_token_binds_raw_bytes_paths_and_file_set
    path = File.join(@dir, "en-US/name.txt")
    stage("en-US/name.txt", "private name")
    args = approved_args
    File.open(path, "a") { |file| file.write("\n") }
    refute_equal 0, upload(args).first
    stage("en-US/name.txt", "private name")
    stage("copyright.txt", "private copyright")
    refute_equal 0, upload(args).first
    File.unlink(File.join(@dir, "copyright.txt"))
    File.rename(path, File.join(@dir, "en-US/subtitle.txt"))
    refute_equal 0, upload(args).first
    assert_empty @writes
  end

  def test_extra_file_beside_metadata_invalidates_staging
    stage("en-US/name.txt", "private name")
    args = approved_args
    File.write(File.join(@staging, "extra.txt"), "private text")
    refute_equal 0, upload(args).first
    assert_empty @writes
  end

  def test_loaded_app_must_match_the_approved_bundle
    stage("en-US/name.txt", "private name")
    @app.stub(:bundle_id, "other.app") do
      status, output = upload
      refute_equal 0, status
      assert_includes output, "0 fields written"
      refute_includes output, "other.app"
      assert_empty @writes
    end
  end

  def test_token_cannot_be_reused_for_another_bundle
    stage("en-US/name.txt", "private name")
    args = approved_args
    args[1] = "other.app"
    ENV["LK_PUBLISH_UNVERIFIED"] = "apple:other.app"
    @app.define_singleton_method(:bundle_id) { "other.app" }
    status, output = upload(args)
    refute_equal 0, status
    assert_includes output, "write approval mismatch"
    assert_empty @writes
  end

  def test_token_cannot_be_reused_for_another_target
    stage("en-US/name.txt", "private name")
    args = approved_args
    @pins["id"] = "replacement"
    File.write(args[-2], JSON.generate(@pins))
    @version.define_singleton_method(:id) { "replacement" }
    refute_equal 0, upload(args).first
    assert_empty @writes
  end

  def test_write_requires_scoped_override_and_consumes_approval
    stage("en-US/name.txt", "private name")
    args = approved_args
    [nil, "apple:other"].each do |override|
      ENV["LK_PUBLISH_UNVERIFIED"] = override
      refute_equal 0, upload(args).first
      assert_empty @writes
    end
    ENV["LK_PUBLISH_UNVERIFIED"] = "apple:test.app"
    assert_equal 0, upload(args).first
    refute_equal 0, upload(args).first
    assert_equal 1, @writes.size
  end

  def test_state_allowlist
    stage("en-US/name.txt", "private name")
    %w[PREPARE_FOR_SUBMISSION DEVELOPER_REJECTED REJECTED].each do |state|
      @model.app_version_state = state
      assert_equal 0, upload.first
    end
    @writes.clear
    %w[WAITING_FOR_REVIEW IN_REVIEW UNKNOWN].each do |state|
      @model.app_version_state = state
      status, output = upload
      refute_equal 0, status
      assert_includes output, state
      assert_empty @writes
    end
  end

  def test_write_requires_matching_nonempty_approval
    stage("en-US/name.txt", "private name")
    [nil, "", "different", "cd" * 32].each do |secret|
      refute_equal 0, upload(approval_secret: secret).first
    end
    refute_equal 0, upload(["test.app", "private-key-path", @dir]).first
    assert_empty @writes
  end

  def test_symlink_in_staging_path_refused
    Dir.mktmpdir do |parent|
      link = File.join(parent, "link")
      File.symlink(@staging, link)
      stage("en-US/name.txt", "private name")
      args = approved_args
      args[3] = File.join(link, "metadata")
      args[4] = File.join(link, "apple-target.json")
      status, = upload(args)
      refute_equal 0, status
      assert_empty @writes
    end
  end

  def test_staged_review_information_refused_before_any_write
    stage("review_information/notes.txt", "private review")
    stage("en-US/name.txt", "private name")
    status, output = upload
    refute_equal 0, status
    refute_includes output, "private"
    assert_empty @writes
  end

  def test_verified_fastlane_versions
    %w[2.240.1 2.241.0 2.242.0].each { |v| AppleTextUpload.verify_fastlane!(v) }
    %w[2.240.0 2.242.1].each do |v|
      error = assert_raises(AppleTextUpload::Refusal) { AppleTextUpload.verify_fastlane!(v) }
      assert_includes error.message, v
    end
  end

  def test_unverified_loaded_gem_stops_before_writing
    loaded = Fastlane::VERSION
    Fastlane.send(:remove_const, :VERSION)
    Fastlane.const_set(:VERSION, "2.242.1")
    stage("en-US/name.txt", "private name")
    status, output = upload
    refute_equal 0, status
    assert_includes output, "unsupported fastlane 2.242.1"
    assert_empty @writes
  ensure
    Fastlane.send(:remove_const, :VERSION)
    Fastlane.const_set(:VERSION, loaded)
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
