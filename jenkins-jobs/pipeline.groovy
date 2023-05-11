@Library('jenkins-libs@jc') _

poetryProject {

    config {
        publishing {
            autoPublishDeveloperBranch = true
        }
    }

    poetryModule('./') {
        test {
            junitArtefacts = ['.test-report/test-report.xml']
        }
    }
}