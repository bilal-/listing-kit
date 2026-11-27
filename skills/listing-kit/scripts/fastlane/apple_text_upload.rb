# frozen_string_literal: true

require "json"
require "openssl"

module AppleTextUpload
  # fastlane 2.242.0, deliver/lib/deliver/upload_metadata.rb:11-30.
  VERSION = %w[description keywords promotional_text support_url marketing_url].to_h { |key| [key, key] }
            .merge("release_notes" => "whats_new").freeze
  INFO = {"name" => "name", "subtitle" => "subtitle", "privacy_url" => "privacy_policy_url"}.freeze
  LOCALE = /\A[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\z/
  ID = /\A[A-Za-z0-9-]{1,128}\z/.freeze
  STATE = /\A[A-Z_]{1,64}\z/.freeze
  VERIFIED_FASTLANE = (Gem::Version.new("2.240.1")..Gem::Version.new("2.242.0")).freeze
  WRITE_STATES = %w[PREPARE_FOR_SUBMISSION DEVELOPER_REJECTED REJECTED].freeze

  class Refusal < StandardError; end

  def self.staged_fields(folder)
    raise Refusal, "invalid staged directory" unless File.realpath(folder) == File.expand_path(folder)
    fields = {}
    hashes = {}
    Dir.children(folder).sort.each do |entry|
      path = File.join(folder, entry)
      if File.directory?(path) && !File.symlink?(path) && LOCALE.match?(entry) && entry != "default"
        Dir.children(path).sort.each do |filename|
          field = File.basename(filename, ".txt")
          unless filename == "#{field}.txt" && (INFO.key?(field) || VERSION.key?(field))
            raise Refusal, "change unsupported fields in App Store Connect"
          end
          fields[[entry, field]] = read_field(File.join(path, filename), "metadata/#{entry}/#{filename}", hashes)
        end
      elsif entry == "copyright.txt"
        fields[[nil, "copyright"]] = read_field(path, "metadata/copyright.txt", hashes)
      else
        raise Refusal, "change unsupported fields in App Store Connect"
      end
    end
    [fields, hashes]
  end

  def self.read_field(path, relative, hashes)
    raise Refusal, "invalid staged file" unless File.file?(path) && !File.symlink?(path)
    raw = File.binread(path)
    hashes[relative] = OpenSSL::Digest::SHA256.hexdigest(raw)
    value = raw.force_encoding("UTF-8")
    raise Refusal, "invalid staged text" unless value.valid_encoding?
    value = value.strip
    raise Refusal, "empty staged field" if value.empty?
    value
  end

  def self.verify_fastlane!(loaded)
    raise Refusal, "unsupported fastlane #{loaded}" unless VERIFIED_FASTLANE.cover?(Gem::Version.new(loaded))
  end

  def self.by_locale(resources)
    resources.each_with_object({}) do |resource, indexed|
      locale = resource.locale
      unless LOCALE.match?(locale) && ID.match?(resource.id) && !indexed.key?(locale)
        raise Refusal, "invalid Apple localization"
      end
      indexed[locale] = resource
    end
  end

  def self.run(args, output)
    mode, identifier, key_path, folder, pins_path, token_arg = args
    written = 0
    describe = mode == "describe" && args.size == 3
    unless describe
      raise Refusal, "invalid writer arguments" unless mode == "write" && args.size == 6
      secret = ENV["LK_APPLE_WRITE_SECRET"]
      unless ENV["LK_PUBLISH_UNVERIFIED"] == "apple:#{identifier}" && /\A[0-9a-f]{64}\z/.match?(secret) &&
             /\A[0-9a-f]{64}\z/.match?(token_arg)
        raise Refusal, "write approval missing"
      end
    end
    verify_fastlane!(Fastlane::VERSION)
    unless describe
      staging = File.dirname(folder)
      unless folder == File.join(staging, "metadata") && File.realpath(staging) == staging &&
             pins_path == File.join(staging, "apple-target.json") && File.file?(pins_path) && !File.symlink?(pins_path)
        raise Refusal, "write approval missing"
      end
      raise Refusal, "unexpected staged file" unless Dir.children(staging).sort == %w[apple-target.json metadata]
      pins = JSON.parse(File.binread(pins_path))
      fields, hashes = staged_fields(folder)
    end
    # deliver/lib/deliver/runner.rb:34,36 (API-key login only).
    token = Spaceship::ConnectAPI::Token.from(hash: nil, filepath: key_path)
    raise Refusal, "API key unavailable" unless token
    Spaceship::ConnectAPI.token = token
    # deliver/lib/deliver/detect_values.rb:46.
    app = Spaceship::ConnectAPI::App.find(identifier)
    raise Refusal, "app unavailable" unless app && app.bundle_id == identifier
    # deliver/lib/deliver/options.rb:95-100 and upload_metadata.rb:99,446.
    platform = Spaceship::ConnectAPI::Platform.map("ios")
    version = app.get_edit_app_store_version(platform: platform, includes: Spaceship::ConnectAPI::AppStoreVersion::ESSENTIAL_INCLUDES + ",appClipDefaultExperience")
    raise Refusal, "editable version unavailable" unless version

    state = version.app_version_state
    if describe
      # deliver download_metadata selects the latest iOS version. Only use
      # that copy for a text approval when it describes this editable ID.
      latest = app.get_latest_app_store_version(platform: platform)
      raise Refusal, "download version differs from editable version" unless latest && latest.id == version.id
    end
    raise Refusal, "invalid version identity" unless ID.match?(version.id) && STATE.match?(state)
    raise Refusal, "editable version changed" unless describe || version.id == pins.fetch("id")
    unless describe || WRITE_STATES.include?(state)
      raise Refusal, "Apple text writes refused in #{state}"
    end
    # Resolve once. The objects checked here are also the PATCH destinations.
    info = app.fetch_edit_app_info
    raise Refusal, "editable app info unavailable" unless info && ID.match?(info.id) && STATE.match?(info.state)
    raise Refusal, "editable app info changed" unless describe || info.id == pins.fetch("appInfoId")
    versions = by_locale(version.get_app_store_version_localizations)
    infos = by_locale(info.get_app_info_localizations)
    localizations = (versions.keys | infos.keys).sort.map { |locale| [locale, versions[locale]&.id, infos[locale]&.id] }
    if describe
      raise Refusal, "invalid version identity" unless /\A[0-9]+(?:\.[0-9]+)*\z/.match?(version.version_string)
      output.puts "version #{version.version_string} #{version.id} #{state}", "appInfo #{info.id} #{info.state}"
      localizations.each { |row| output.puts "locale " + row.map { |id| id || "." }.join(" ") }
      return 0
    end

    patches = {}
    fields.each do |(locale, field), value|
      raise Refusal, "missing locale #{locale}" if locale && !versions.key?(locale)
      if INFO.key?(field)
        target = infos.fetch(locale) { raise Refusal, "missing locale #{locale}" }
        attribute = INFO.fetch(field)
      elsif locale
        target = versions.fetch(locale)
        attribute = VERSION.fetch(field)
      else
        target = version
        attribute = "copyright"
      end
      (patches[[locale, target]] ||= []) << [field, attribute, value]
    end
    raise Refusal, "Apple localization changed" unless localizations == pins.fetch("localizations")
    # Defence in depth, not a security boundary: whoever holds the API key can change the store directly.
    message = JSON.generate([app.bundle_id, version.id, info.id, localizations, hashes.sort])
    expected = OpenSSL::HMAC.hexdigest("SHA256", secret, message)
    raise Refusal, "write approval mismatch" unless OpenSSL.fixed_length_secure_compare(expected, token_arg)

    # Only one writer can consume this private approval before its first PATCH.
    File.unlink(pins_path)
    patches.each do |(locale, target), entries|
      # deliver/lib/deliver/upload_metadata.rb:212 (version, only copyright),
      # :220 (version localization), :232 (app-info localization).
      target.update(attributes: entries.to_h { |_, attribute, value| [attribute, value] })
      written += entries.size
      entries.each { |field, _, _| output.puts [locale, field].compact.join(" ") }
    end
    0
  rescue Refusal => e
    output.puts e.message
    1
  rescue StandardError
    output.puts "Apple text update failed"
    1
  ensure
    output.puts "#{written} fields written" unless describe
  end
end

if $PROGRAM_NAME == __FILE__
  # Spaceship logs API bodies to stdout under VERBOSE. Silence both native
  # descriptors before loading the gem and reserve a stream for our own report.
  report = STDOUT.dup
  report.sync = true
  STDOUT.reopen(File::NULL, "w")
  STDERR.reopen(File::NULL, "w")
  ENV["VERBOSE"] = "1"
  unless (ARGV.first == "describe" && ARGV.size == 3) || (ARGV.first == "write" && ARGV.size == 6)
    report.puts "invalid writer arguments", "0 fields written"
    exit 1
  end
  begin
    require "fastlane"
    require "spaceship"
  rescue LoadError, StandardError
    report.puts "fastlane unavailable", "0 fields written"
    exit 1
  end
  exit AppleTextUpload.run(ARGV, report)
end
