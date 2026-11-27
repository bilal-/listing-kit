# frozen_string_literal: true

module AppleTextUpload
  # fastlane 2.242.0, deliver/lib/deliver/upload_metadata.rb:11-30.
  VERSION = %w[description keywords promotional_text support_url marketing_url].to_h { |key| [key, key] }
            .merge("release_notes" => "whats_new").freeze
  INFO = {"name" => "name", "subtitle" => "subtitle", "privacy_url" => "privacy_policy_url"}.freeze
  LOCALE = /\A[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\z/
  class Refusal < StandardError; end

  def self.staged_fields(folder)
    fields = {}
    Dir.children(folder).sort.each do |entry|
      path = File.join(folder, entry)
      if File.directory?(path) && !File.symlink?(path) && LOCALE.match?(entry) && entry != "default"
        Dir.children(path).sort.each do |filename|
          field = File.basename(filename, ".txt")
          unless filename == "#{field}.txt" && (INFO.key?(field) || VERSION.key?(field))
            raise Refusal, "change unsupported fields in App Store Connect"
          end
          fields[[entry, field]] = read_field(File.join(path, filename))
        end
      elsif entry == "copyright.txt"
        fields[[nil, "copyright"]] = read_field(path)
      else
        raise Refusal, "change unsupported fields in App Store Connect"
      end
    end
    fields
  end

  def self.read_field(path)
    raise Refusal, "invalid staged file" unless File.file?(path) && !File.symlink?(path)
    value = File.read(path, encoding: "UTF-8").strip
    raise Refusal, "invalid staged text" unless value.valid_encoding?
    raise Refusal, "empty staged field" if value.empty?
    value
  end

  def self.run(identifier, key_path, folder, output)
    written = 0
    fields = staged_fields(folder)
    # deliver/lib/deliver/runner.rb:34,36 (API-key login only).
    token = Spaceship::ConnectAPI::Token.from(hash: nil, filepath: key_path)
    raise Refusal, "API key unavailable" unless token
    Spaceship::ConnectAPI.token = token
    # deliver/lib/deliver/detect_values.rb:46.
    app = Spaceship::ConnectAPI::App.find(identifier)
    raise Refusal, "app unavailable" unless app
    # deliver/lib/deliver/options.rb:95-100 and upload_metadata.rb:99,446.
    platform = Spaceship::ConnectAPI::Platform.map("ios")
    version = app.get_edit_app_store_version(platform: platform, includes: Spaceship::ConnectAPI::AppStoreVersion::ESSENTIAL_INCLUDES + ",appClipDefaultExperience")
    raise Refusal, "editable version unavailable" unless version

    # Resolve every destination before issuing the first PATCH.
    locales = fields.keys.map(&:first).compact.uniq
    unless locales.empty?
      # deliver/lib/deliver/upload_metadata.rb:563.
      versions = version.get_app_store_version_localizations.to_h { |loc| [loc.locale, loc] }
      locales.each { |locale| raise Refusal, "missing locale #{locale}" unless versions.key?(locale) }
    end
    if fields.keys.any? { |_, field| INFO.key?(field) }
      # deliver/lib/deliver/upload_metadata.rb:452,530.
      info = app.fetch_edit_app_info
      raise Refusal, "editable app info unavailable" unless info
      infos = info.get_app_info_localizations.to_h { |loc| [loc.locale, loc] }
    end
    patches = {}
    fields.each do |(locale, field), value|
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
    output.puts "#{written} fields written"
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
  unless ARGV.size == 3
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
  exit AppleTextUpload.run(*ARGV, report)
end
