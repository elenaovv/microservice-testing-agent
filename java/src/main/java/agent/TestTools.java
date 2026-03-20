package agent;

import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.agent.tool.P;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class TestTools {

    private static final Path GENERATED_TESTS_DIR = Paths.get("generated-tests");
    private static final Path TEST_RESULTS_DIR = Paths.get("test-results");

    final List<Map<String, String>> actionLog = new ArrayList<>();
    private final Map<String, Long> timers = new HashMap<>();

    @Tool("Log a browser action and the reason it was taken. Call after every meaningful browser interaction.")
    public String logAction(
            @P("Short description of the action taken") String action,
            @P("Why this action was taken") String note) {
        actionLog.add(Map.of("action", action, "note", note));
        log("📝 " + action + " — " + note);
        return "Logged: " + action;
    }

    @Tool("Start a named timer to measure how long a step takes.")
    public String startTimer(@P("Timer name") String name) {
        timers.put(name, System.currentTimeMillis());
        return "Timer '" + name + "' started";
    }

    @Tool("Stop a named timer and return elapsed seconds.")
    public String stopTimer(@P("Timer name") String name) {
        Long start = timers.remove(name);
        if (start == null) return "No timer named '" + name + "'";
        double elapsed = (System.currentTimeMillis() - start) / 1000.0;
        log(String.format("⏱ %s: %.1fs", name, elapsed));
        return String.format("'%s' took %.1fs", name, elapsed);
    }

    @Tool("Create a Playwright Java test file in generated-tests/. Filename must end with .java.")
    public String createJavaFile(
            @P("Filename ending in .java") String filename,
            @P("Full Java source code") String code) throws IOException {
        Files.createDirectories(GENERATED_TESTS_DIR);
        Path path = GENERATED_TESTS_DIR.resolve(filename);
        Files.writeString(path, code);
        log("📄 Written " + path + " (" + code.lines().count() + " lines)");
        return "Created " + path;
    }

    @Tool("Compile and run a Java test file from generated-tests/. Returns output and screenshot path on failure.")
    public String runJavaFile(@P("Filename to compile and run") String filename) throws IOException, InterruptedException {
        Path path = GENERATED_TESTS_DIR.resolve(filename);
        if (!Files.exists(path)) return "File not found: " + path;

        log("☕ Compiling " + filename + " ...");
        Process compile = new ProcessBuilder("javac", "-cp", classpathWithPlaywright(), filename)
                .directory(GENERATED_TESTS_DIR.toFile())
                .redirectErrorStream(true)
                .start();
        String compileOut = new String(compile.getInputStream().readAllBytes());
        if (compile.waitFor() != 0) {
            logOutput(compileOut);
            return "Compile error:\n" + compileOut;
        }

        String classname = filename.replace(".java", "");
        log("▶ Running " + classname + " ...");
        Process run = new ProcessBuilder("java", "-cp", ".:" + classpathWithPlaywright(), classname)
                .directory(GENERATED_TESTS_DIR.toFile())
                .redirectErrorStream(true)
                .start();
        String runOut = new String(run.getInputStream().readAllBytes());
        int runExit = run.waitFor();
        logOutput(runOut);

        String status = runExit == 0 ? "✓ Passed" : "✗ Failed (exit " + runExit + ")";
        log(status);

        String result = (runOut.isEmpty() ? "" : runOut + "\n") + status;

        if (runExit != 0) {
            String screenshot = findLatestScreenshot();
            if (screenshot != null) {
                log("📸 Screenshot on failure: " + screenshot);
                result += "\nScreenshot saved at: " + screenshot +
                          "\nDescribe what you see in this screenshot to understand the failure.";
            }
        }

        return result;
    }

    public String actionSummary() {
        if (actionLog.isEmpty()) return "No actions logged.";
        StringBuilder sb = new StringBuilder();
        for (var entry : actionLog) {
            sb.append("- ").append(entry.get("action")).append(": ").append(entry.get("note")).append("\n");
        }
        return sb.toString();
    }

    private static String classpathWithPlaywright() throws IOException {
        // Find playwright jar from maven local repo or classpath
        String home = System.getProperty("user.home");
        Path playwrightJar = Paths.get(home, ".m2/repository/com/microsoft/playwright/playwright")
                .toFile().exists()
                ? findFirstJar(Paths.get(home, ".m2/repository/com/microsoft/playwright/playwright"))
                : null;
        return playwrightJar != null ? playwrightJar.toString() : ".";
    }

    private static Path findFirstJar(Path dir) throws IOException {
        if (!Files.exists(dir)) return null;
        try (var stream = Files.walk(dir)) {
            return stream.filter(p -> p.toString().endsWith(".jar") && !p.toString().contains("sources"))
                    .findFirst().orElse(null);
        }
    }

    private static String findLatestScreenshot() throws IOException {
        if (!Files.exists(TEST_RESULTS_DIR)) return null;
        try (var stream = Files.walk(TEST_RESULTS_DIR)) {
            return stream
                    .filter(p -> p.toString().endsWith(".png"))
                    .max((a, b) -> {
                        try { return Files.getLastModifiedTime(a).compareTo(Files.getLastModifiedTime(b)); }
                        catch (IOException e) { return 0; }
                    })
                    .map(Path::toString)
                    .orElse(null);
        }
    }

    private static void log(String msg) {
        System.out.println("\033[90m    " + msg + "\033[0m");
        System.out.flush();
    }

    private static void logOutput(String output) {
        for (String line : output.strip().split("\n")) log(line);
    }
}
