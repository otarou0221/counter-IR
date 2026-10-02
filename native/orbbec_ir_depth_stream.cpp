#include "libobsensor/hpp/Context.hpp"
#include "libobsensor/hpp/Device.hpp"
#include "libobsensor/hpp/Error.hpp"
#include "libobsensor/hpp/Frame.hpp"
#include "libobsensor/hpp/Pipeline.hpp"
#include "libobsensor/hpp/Sensor.hpp"
#include "libobsensor/hpp/StreamProfile.hpp"

#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#pragma pack(push, 1)
struct FrameHeader {
    char     magic[4];
    uint32_t width;
    uint32_t height;
    uint32_t channels;
    uint32_t payloadSize;
    uint64_t frameIndex;
};
#pragma pack(pop)

namespace {
struct Options {
    std::string ip;
    int         port        = 8090;
    int         depthWidth  = 512;
    int         depthHeight = 512;
    int         fps         = 15;
    int         timeoutMs   = 1000;
    int         maxFrames   = 0;
};

int parseInt(const char *value, const char *name) {
    try {
        return std::stoi(value);
    }
    catch(...) {
        std::cerr << "Invalid integer for " << name << ": " << value << std::endl;
        std::exit(2);
    }
}

Options parseArgs(int argc, char **argv) {
    Options options;
    for(int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        auto requireValue = [&](const char *name) -> const char * {
            if(i + 1 >= argc) {
                std::cerr << "Missing value for " << name << std::endl;
                std::exit(2);
            }
            return argv[++i];
        };

        if(arg == "--ip") {
            options.ip = requireValue("--ip");
        }
        else if(arg == "--port") {
            options.port = parseInt(requireValue("--port"), "--port");
        }
        else if(arg == "--width" || arg == "--depth-width") {
            options.depthWidth = parseInt(requireValue(arg.c_str()), arg.c_str());
        }
        else if(arg == "--height" || arg == "--depth-height") {
            options.depthHeight = parseInt(requireValue(arg.c_str()), arg.c_str());
        }
        else if(arg == "--fps") {
            options.fps = parseInt(requireValue("--fps"), "--fps");
        }
        else if(arg == "--timeout-ms") {
            options.timeoutMs = parseInt(requireValue("--timeout-ms"), "--timeout-ms");
        }
        else if(arg == "--max-frames") {
            options.maxFrames = parseInt(requireValue("--max-frames"), "--max-frames");
        }
        else if(arg == "--help" || arg == "-h") {
            std::cerr << "Usage: " << argv[0]
                      << " --ip 192.168.253.7 [--port 8090] [--width 512] [--height 512]"
                      << " [--fps 15] [--timeout-ms 1000] [--max-frames 0]"
                      << std::endl;
            std::exit(0);
        }
        else {
            std::cerr << "Unknown argument: " << arg << std::endl;
            std::exit(2);
        }
    }

    if(options.port <= 0 || options.port > 65535 || options.depthWidth <= 0 || options.depthHeight <= 0 || options.fps <= 0
       || options.timeoutMs <= 0) {
        std::cerr << "Port must be 1-65535; width, height, depth size, fps, and timeout must be positive" << std::endl;
        std::exit(2);
    }
    return options;
}

template <typename T>
void writeFrame(const char magic[4], uint32_t width, uint32_t height, uint32_t channels, uint64_t index, const std::vector<T> &payload) {
    FrameHeader header{};
    header.magic[0]     = magic[0];
    header.magic[1]     = magic[1];
    header.magic[2]     = magic[2];
    header.magic[3]     = magic[3];
    header.width        = width;
    header.height       = height;
    header.channels     = channels;
    header.payloadSize  = static_cast<uint32_t>(payload.size() * sizeof(T));
    header.frameIndex   = index;

    std::cout.write(reinterpret_cast<const char *>(&header), sizeof(header));
    std::cout.write(reinterpret_cast<const char *>(payload.data()), static_cast<std::streamsize>(header.payloadSize));
    std::cout.flush();
}

std::string intrinsicJson(const std::shared_ptr<ob::VideoStreamProfile> &profile) {
    auto intrinsic = profile->getIntrinsic();
    auto distortion = profile->getDistortion();
    std::ostringstream out;
    out << std::fixed << std::setprecision(6);
    out << "{"
        << "\"width\":" << profile->width() << ","
        << "\"height\":" << profile->height() << ","
        << "\"fx\":" << intrinsic.fx << ","
        << "\"fy\":" << intrinsic.fy << ","
        << "\"cx\":" << intrinsic.cx << ","
        << "\"cy\":" << intrinsic.cy << ","
        << "\"distortion\":{"
        << "\"k1\":" << distortion.k1 << ","
        << "\"k2\":" << distortion.k2 << ","
        << "\"k3\":" << distortion.k3 << ","
        << "\"k4\":" << distortion.k4 << ","
        << "\"k5\":" << distortion.k5 << ","
        << "\"k6\":" << distortion.k6 << ","
        << "\"p1\":" << distortion.p1 << ","
        << "\"p2\":" << distortion.p2
        << "}}";
    return out.str();
}

void writeIntrinsicsMetadata(
    const std::shared_ptr<ob::VideoStreamProfile> &irProfile,
    const std::shared_ptr<ob::VideoStreamProfile> &depthProfile
) {
    std::ostringstream out;
    out << "{"
        << "\"version\":1,"
        << "\"align_depth_to_color\":false,"
        << "\"point_cloud_sensor\":\"depth\","
        << "\"ir\":" << intrinsicJson(irProfile) << ","
        << "\"color\":null,"
        << "\"depth\":" << intrinsicJson(depthProfile)
        << "}";
    const std::string payload = out.str();
    const std::vector<uint8_t> bytes(payload.begin(), payload.end());
    writeFrame("OBIN", static_cast<uint32_t>(bytes.size()), 1, 1, 0, bytes);
}

std::vector<uint16_t> copyInfrared(const std::shared_ptr<ob::IRFrame> &frame) {
    const uint32_t width  = frame->width();
    const uint32_t height = frame->height();
    const size_t   pixels = static_cast<size_t>(width) * static_cast<size_t>(height);
    if(frame->format() != OB_FORMAT_Y16 || frame->dataSize() < pixels * sizeof(uint16_t)) {
        throw std::runtime_error("Unsupported IR frame; expected Y16");
    }
    const auto *src = static_cast<const uint16_t *>(frame->data());
    return std::vector<uint16_t>(src, src + pixels);
}

std::vector<uint16_t> convertDepthToMillimeters(const std::shared_ptr<ob::DepthFrame> &frame) {
    const uint32_t width  = frame->width();
    const uint32_t height = frame->height();
    const size_t   pixels = static_cast<size_t>(width) * static_cast<size_t>(height);
    const auto    *src    = static_cast<const uint16_t *>(frame->data());
    const auto     size   = frame->dataSize();
    const float    scale  = frame->getValueScale() > 0 ? frame->getValueScale() : 1.0f;

    if(frame->format() != OB_FORMAT_Y16) {
        throw std::runtime_error("Unsupported depth frame format. Use Y16 profile.");
    }
    if(size < pixels * sizeof(uint16_t)) {
        throw std::runtime_error("Depth frame payload is smaller than expected");
    }

    std::vector<uint16_t> depthMm(pixels);
    for(size_t i = 0; i < pixels; i++) {
        float depth = static_cast<float>(src[i]) * scale;
        if(depth < 0) {
            depth = 0;
        }
        if(depth > 65535.0f) {
            depth = 65535.0f;
        }
        depthMm[i] = static_cast<uint16_t>(depth + 0.5f);
    }
    return depthMm;
}

std::shared_ptr<ob::VideoStreamProfile> getRawDepthProfile(ob::Pipeline &pipe, const Options &options) {
    auto depthProfiles = pipe.getStreamProfileList(OB_SENSOR_DEPTH);
    return depthProfiles->getVideoStreamProfile(options.depthWidth, options.depthHeight, OB_FORMAT_Y16, options.fps);
}

struct PipelineSetup {
    std::shared_ptr<ob::Config>             config;
    std::shared_ptr<ob::VideoStreamProfile> irProfile;
    std::shared_ptr<ob::VideoStreamProfile> depthProfile;
};

PipelineSetup preparePipeline(ob::Pipeline &pipe, const Options &options) {
    PipelineSetup setup;
    setup.config = std::make_shared<ob::Config>();

    setup.depthProfile = getRawDepthProfile(pipe, options);
    auto irProfiles = pipe.getStreamProfileList(OB_SENSOR_IR);
    setup.irProfile = irProfiles->getVideoStreamProfile(
        options.depthWidth, options.depthHeight, OB_FORMAT_Y16, options.fps
    );
    if(setup.irProfile->width() != setup.depthProfile->width()
       || setup.irProfile->height() != setup.depthProfile->height()) {
        throw std::runtime_error("IR and depth profiles must have identical dimensions");
    }
    setup.config->enableStream(setup.irProfile);
    setup.config->enableStream(setup.depthProfile);
    // FULL_FRAME_REQUIRE truncates WFOV depth on the current Femto Mega/SDK.
    // Accept SDK FrameSets as they arrive; the mailbox keeps synchronized pairs.
    setup.config->setFrameAggregateOutputMode(OB_FRAME_AGGREGATE_OUTPUT_ANY_SITUATION);
    return setup;
}

constexpr uint64_t kMaxPairTimestampDifferenceUs = 10000;

class LatestFrameSetMailbox {
public:
    void publish(std::shared_ptr<ob::FrameSet> frameSet) {
        if(frameSet == nullptr) {
            return;
        }
        auto irFrame = frameSet->irFrame();
        auto depthFrame = frameSet->depthFrame();
        if(irFrame == nullptr || depthFrame == nullptr) {
            return;
        }
        const uint64_t irTimeUs = irFrame->timeStampUs();
        const uint64_t depthTimeUs = depthFrame->timeStampUs();
        if(irTimeUs == 0 || depthTimeUs == 0) {
            return;
        }
        const uint64_t timeDifferenceUs = irTimeUs > depthTimeUs
            ? irTimeUs - depthTimeUs : depthTimeUs - irTimeUs;
        // At 15 fps, adjacent captures are about 67 ms apart. Reject mismatched
        // exposures while allowing small timestamp jitter from other profiles.
        if(timeDifferenceUs > kMaxPairTimestampDifferenceUs) {
            return;
        }
        {
            std::lock_guard<std::mutex> lock(mutex_);
            latest_ = std::move(frameSet);
            sequence_++;
        }
        ready_.notify_one();
    }

    std::shared_ptr<ob::FrameSet> waitNext(uint64_t &consumedSequence, int timeoutMs) {
        std::unique_lock<std::mutex> lock(mutex_);
        const bool available = ready_.wait_for(
            lock,
            std::chrono::milliseconds(timeoutMs),
            [&]() { return sequence_ > consumedSequence; }
        );
        if(!available) {
            return nullptr;
        }
        consumedSequence = sequence_;
        return latest_;
    }

private:
    std::mutex                    mutex_;
    std::condition_variable       ready_;
    std::shared_ptr<ob::FrameSet> latest_;
    uint64_t                      sequence_ = 0;
};

int streamFrames(ob::Pipeline &pipe, const PipelineSetup &setup, const Options &options) {
    LatestFrameSetMailbox mailbox;
    pipe.start(setup.config, [&](std::shared_ptr<ob::FrameSet> frameSet) {
        mailbox.publish(std::move(frameSet));
    });

    int      emitted = 0;
    int      emptyWaits = 0;
    uint64_t consumedSequence = 0;
    while(options.maxFrames <= 0 || emitted < options.maxFrames) {
        auto frameSet = mailbox.waitNext(consumedSequence, options.timeoutMs);
        if(frameSet == nullptr) {
            emptyWaits++;
            if(emptyWaits * options.timeoutMs >= 15000) {
                std::cerr << "No synchronized IR/depth pair received for " << emptyWaits * options.timeoutMs << " ms" << std::endl;
                pipe.stop();
                return 3;
            }
            continue;
        }

        auto irFrame = frameSet->irFrame();
        auto depthFrame = frameSet->depthFrame();
        if(irFrame == nullptr || depthFrame == nullptr) {
            // The mailbox filters incomplete sets; retain this safety check.
            continue;
        }

        emptyWaits = 0;
        if(irFrame->width() != depthFrame->width() || irFrame->height() != depthFrame->height()) {
            throw std::runtime_error("IR and depth frame dimensions differ");
        }
        auto infrared = copyInfrared(irFrame);
        auto depthMm = convertDepthToMillimeters(depthFrame);
        writeFrame("OBIF", irFrame->width(), irFrame->height(), 1, irFrame->index(), infrared);
        writeFrame("OBDF", depthFrame->width(), depthFrame->height(), 1, depthFrame->index(), depthMm);
        emitted++;
    }

    pipe.stop();
    return 0;
}

}  // namespace

int main(int argc, char **argv) try {
    auto options = parseArgs(argc, argv);

    ob::Context::setLoggerSeverity(OB_LOG_SEVERITY_OFF);
    ob::Context::setLoggerToConsole(OB_LOG_SEVERITY_OFF);

    std::shared_ptr<ob::Device> device;
    ob::Context                 ctx;
    if(!options.ip.empty()) {
        std::cerr << "Connecting to Orbbec network device: " << options.ip << ":" << options.port << std::endl;
        device = ctx.createNetDevice(options.ip.c_str(), static_cast<uint16_t>(options.port));
    }
    else {
        std::cerr << "Searching for local Orbbec device" << std::endl;
        auto devices = ctx.queryDeviceList();
        if(devices->deviceCount() == 0) {
            std::cerr << "No Orbbec device found" << std::endl;
            return 1;
        }
        device = devices->getDevice(0);
    }

    ob::Pipeline pipe(device);
    auto setup = preparePipeline(pipe, options);
    std::cerr << "Active IR/depth profile " << setup.depthProfile->width() << "x" << setup.depthProfile->height()
              << "@" << setup.depthProfile->fps() << std::endl;
    writeIntrinsicsMetadata(setup.irProfile, setup.depthProfile);
    std::cerr << "Starting Orbbec Active IR/depth streams" << std::endl;
    // The official network-device sample uses the callback API. Keep SDK-owned
    // acquisition work in that callback and process only the latest synchronized pair.
    std::cerr << "Waiting for Orbbec frames" << std::endl;
    return streamFrames(pipe, setup, options);
}
catch(ob::Error &e) {
    std::cerr << "Orbbec SDK error\n"
              << "function: " << e.getName() << "\n"
              << "args: " << e.getArgs() << "\n"
              << "message: " << e.getMessage() << "\n"
              << "type: " << e.getExceptionType() << std::endl;
    return 1;
}
catch(std::exception &e) {
    std::cerr << "Error: " << e.what() << std::endl;
    return 1;
}
