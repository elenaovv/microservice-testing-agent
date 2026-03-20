package agent;

import dev.langchain4j.agent.tool.Tool;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public class TestTools {

    private static final Path GENERATED_TESTS_DIR = Paths.get("generated-tests");

    @Tool("Create a Java source file in the generated-tests/ folder. " +
          "For Playwright tests use com.microsoft.playwright — no Selenium, no ChromeDriver. " +
          "For benchmarks write a self-contained main() class. " +
          "Filename must end with .java.")
    public String createJavaFile(String filename, String code) throws IOException {
        Files.createDirectories(GENERATED_TESTS_DIR);
        Path path = GENERATED_TESTS_DIR.resolve(filename);
        Files.writeString(path, code);
        log("📄 Written " + path + " (" + code.lines().count() + " lines)");
        return "Created " + path;
    }

    @Tool("Compile and run a Java file from the generated-tests/ folder. " +
          "Returns full stdout/stderr output including any assertion failures.")
    public String runJavaFile(String filename) throws IOException, InterruptedException {
        Path path = GENERATED_TESTS_DIR.resolve(filename);
        if (!Files.exists(path)) {
            return "File not found: " + path;
        }

        log("☕ Compiling " + filename + " ...");
        ProcessBuilder compileBuilder = new ProcessBuilder("javac", filename)
                .directory(GENERATED_TESTS_DIR.toFile())
                .redirectErrorStream(true);
        Process compileProcess = compileBuilder.start();
        String compileOutput = new String(compileProcess.getInputStream().readAllBytes());
        int compileExit = compileProcess.waitFor();

        if (compileExit != 0) {
            logOutput(compileOutput);
            return "Compile error:\n" + compileOutput;
        }

        String classname = filename.replace(".java", "");
        log("▶ Running " + classname + " ...");
        ProcessBuilder runBuilder = new ProcessBuilder("java", classname)
                .directory(GENERATED_TESTS_DIR.toFile())
                .redirectErrorStream(true);
        Process runProcess = runBuilder.start();
        String runOutput = new String(runProcess.getInputStream().readAllBytes());
        int runExit = runProcess.waitFor();
        logOutput(runOutput);

        String status = runExit == 0 ? "✓ Passed" : "✗ Failed (exit " + runExit + ")";
        log(status);
        return runOutput.isEmpty() ? status : runOutput + "\n" + status;
    }

    private static void log(String msg) {
        System.out.println("\033[90m    " + msg + "\033[0m");
        System.out.flush();
    }

    private static void logOutput(String output) {
        for (String line : output.strip().split("\n")) {
            log(line);
        }
    }
}
